"use client";

import React, { useReducer, useCallback, useRef, useEffect, useState, useMemo } from 'react';
import { cn } from '@/lib/utils'; // Import the cn utility
import ChatMessages from './_components/chat-messages'; // Renamed component
import ChatInput from './_components/chat-input';
import { ChevronDown, Home } from 'lucide-react'; // Icon for scroll button and Home icon
// import { useTypingEffect } from '@/hooks/useTypingEffect'; // Remove hook import

// --- Interfaces (Revert Message interface) --- 
interface Message {
  id: string;
  role: 'user' | 'assistant'; 
  content: string; // Back to just content
  agentName?: string; 
  isLoading?: boolean; 
}

interface ChatMessageInput {
  role: string;
  content: string;
}

// --- Reducer Logic (Revert changes) --- 

interface ChatState {
    messages: { [id: string]: Message }; 
    messageOrder: string[];
    isLoading: boolean;
    loadingMessageId: string | null; 
    currentAssistantMessageId: string | null; 
}

type ChatAction =
    | { type: 'START_ASSISTANT_MESSAGE'; payload: { id: string; agentName?: string } }
    | { type: 'APPEND_DELTA'; payload: { id: string; delta: string } } // Back to APPEND_DELTA
    // | { type: 'UPDATE_DISPLAYED_CONTENT'; payload: { id: string; newContent: string } } // Remove this
    | { type: 'UPDATE_AGENT_NAME'; payload: { id: string; agentName: string } }
    | { type: 'COMPLETE_ASSISTANT_MESSAGE'; payload: { id: string } }
    | { type: 'ADD_USER_MESSAGE'; payload: Message }
    | { type: 'SET_ERROR'; payload: { errorContent: string } }
    | { type: 'RESET_CHAT' }; // Add reset action type

const initialState: ChatState = {
    messages: {},
    messageOrder: [],
    isLoading: false,
    loadingMessageId: null,
    currentAssistantMessageId: null,
};

function chatReducer(state: ChatState, action: ChatAction): ChatState {
    switch (action.type) {
        case 'ADD_USER_MESSAGE':
             // Revert - just add the message as is
            return {
                ...state,
                isLoading: true, 
                messages: { ...state.messages, [action.payload.id]: action.payload },
                messageOrder: [...state.messageOrder, action.payload.id],
            };

        case 'START_ASSISTANT_MESSAGE':
            const newMessage: Message = {
                id: action.payload.id,
                role: 'assistant',
                content: '', // Start empty
                agentName: action.payload.agentName || 'Assistant',
                isLoading: true, 
            };
            return {
                ...state,
                currentAssistantMessageId: action.payload.id, 
                loadingMessageId: action.payload.id, 
                messages: { ...state.messages, [action.payload.id]: newMessage },
                messageOrder: [...state.messageOrder, action.payload.id],
            };

        case 'APPEND_DELTA': // Renamed back
            if (!state.messages[action.payload.id] || state.loadingMessageId !== action.payload.id) return state;
            const msgToAppend = state.messages[action.payload.id];
            return {
                ...state,
                messages: {
                    ...state.messages,
                    [action.payload.id]: {
                        ...msgToAppend,
                        content: msgToAppend.content + action.payload.delta, // Update content directly
                    }
                }
            };
        
        // case 'UPDATE_DISPLAYED_CONTENT': // Remove this case
        //     return state; // Or handle appropriately if needed elsewhere

        case 'UPDATE_AGENT_NAME':
             if (!state.messages[action.payload.id] || state.loadingMessageId !== action.payload.id) return state;
             const msgToUpdateAgent = state.messages[action.payload.id];
            return {
                ...state,
                messages: {
                    ...state.messages,
                    [action.payload.id]: {
                        ...msgToUpdateAgent,
                        agentName: action.payload.agentName,
                    }
                }
            };

        case 'COMPLETE_ASSISTANT_MESSAGE':
            if (state.loadingMessageId !== action.payload.id) return state;
            const completedMsg = state.messages[action.payload.id];
            const updatedMessages = completedMsg ? { 
                ...state.messages, 
                [action.payload.id]: { ...completedMsg, isLoading: false } // Just set isLoading false
            } : state.messages;
            
            return {
                ...state,
                messages: updatedMessages,
                isLoading: false,
                loadingMessageId: null,
                currentAssistantMessageId: null,
            };
        
        case 'SET_ERROR':
             const errorId = `error-${Date.now()}`;
             const errorMessage: Message = {
                 id: errorId,
                 role: 'assistant',
                 content: `Error: ${action.payload.errorContent}`, // Back to content
                 agentName: 'System Error'
             };
            return {
                ...state,
                isLoading: false,
                loadingMessageId: null,
                currentAssistantMessageId: null,
                messages: { ...state.messages, [errorId]: errorMessage },
                messageOrder: [...state.messageOrder, errorId],
            };

        case 'RESET_CHAT': // Add reset case
            console.log("Resetting chat state...");
            return initialState;

        default:
            return state;
    }
}

// --- Page Component --- 
export default function ChatPage() {
    const [state, dispatch] = useReducer(chatReducer, initialState);
    const { messages, messageOrder, isLoading, loadingMessageId } = state;
    const orderedMessages = useMemo(() => 
        messageOrder.map(id => messages[id]).filter(Boolean)
    , [messageOrder, messages]);
    const hasStarted = state.messageOrder.length > 0;

    // Ref for the scrollable message container
    const scrollRef = useRef<HTMLDivElement>(null);
    // Ref for the sentinel element at the end of messages
    const endOfMessagesRef = useRef<HTMLDivElement>(null);
    // State to track if scroll is at the bottom
    const [isAtBottom, setIsAtBottom] = useState(true);
    
    const userJustSentRef = useRef(false); 
    const lastUserSend = useRef<number>(0);

    // Scroll to bottom effect (keep as is for now, depends on loadingMessageId)
    useEffect(() => {
        if (Date.now() - lastUserSend.current < 300) return;
        // Note: This still scrolls based on loadingMessageId, which might need adjustment
        // if we want it purely based on the IntersectionObserver state later.
        if (scrollRef.current && loadingMessageId) { 
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [orderedMessages.length, loadingMessageId]);

    // Intersection Observer effect for scroll position
    useEffect(() => {
        const observer = new IntersectionObserver(
            ([entry]) => {
                // Update state based on whether the sentinel is intersecting (visible)
                setIsAtBottom(entry.isIntersecting);
                console.log(`Intersection Observer: isAtBottom = ${entry.isIntersecting}`);
            },
            {
                root: scrollRef.current, // Observe within the scrollable div
                rootMargin: "0px",
                threshold: 1.0, // Sentinel is fully visible
            }
        );

        const sentinel = endOfMessagesRef.current;
        if (sentinel) {
            observer.observe(sentinel);
        }

        // Cleanup
        return () => {
            if (sentinel) {
                observer.unobserve(sentinel);
            }
            observer.disconnect();
        };
        // Rerun if the scroll container changes (shouldn't often) or chat starts
    }, [hasStarted]); // Depend on hasStarted to observe only when chat active

    // Auto-scroll after every new message
    useEffect(() => {
        if (userJustSentRef.current || isAtBottom) {
            scrollMessagesToBottom(false); // instant scroll
        }
        // Reset the flag so it only runs once after each user send
        if (userJustSentRef.current) userJustSentRef.current = false;
    }, [messageOrder]);

    const scrollToBottom = () => {
        if (scrollRef.current) {
             scrollRef.current.scrollTo({
                 top: scrollRef.current.scrollHeight,
                 behavior: 'smooth'
             });
        }
    };

    // Add handler for resetting chat
    const handleReset = useCallback(() => {
        // Could add confirmation dialog here if desired
        dispatch({ type: 'RESET_CHAT' });
    }, [dispatch]);

    // Helper to scroll the sentinel into view (guaranteed to exist when chat has started)
    const scrollMessagesToBottom = useCallback((smooth: boolean = true) => {
        if (endOfMessagesRef.current) {
            endOfMessagesRef.current.scrollIntoView({
                behavior: smooth ? 'smooth' : 'auto',
                block: 'start', // align sentinel with top of viewport of scroll container
            });
        } else if (scrollRef.current) {
            // Fallback: manual scroll
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, []);

    const handleSendMessage = useCallback(async (userInput: string) => {
        if (state.isLoading) return;

        const newUserMessage: Message = {
            id: `user-${Date.now()}`,
            role: 'user',
            content: userInput, // Back to content
        };
        dispatch({ type: 'ADD_USER_MESSAGE', payload: newUserMessage });

        // Flag so the next useEffect knows we triggered the send
        userJustSentRef.current = true;

        // Immediately record the time of this send
        lastUserSend.current = Date.now();

        // Schedule an auto-scroll to the bottom so the newly sent message is fully visible
        requestAnimationFrame(() => {
            scrollMessagesToBottom(true);
        });

        const newAssistantMsgId = `assistant-${Date.now()}-${Math.random()}`;
        dispatch({ type: 'START_ASSISTANT_MESSAGE', payload: { id: newAssistantMsgId } });

        // Prepare history - use content field
        const currentMessagesArray = orderedMessages;
        const historyForBackend: ChatMessageInput[] = currentMessagesArray.map(msg => ({
            role: msg.role,
            content: msg.content, // Use content
        }));

        const requestBody = {
             user_message: userInput,
             history: historyForBackend
         };

        try {
            const response = await fetch('http://localhost:8000/chat/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                },
                body: JSON.stringify(requestBody),
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            if (!response.body) throw new Error("Response body is null");

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            const assistantMessageIdForThisStream = newAssistantMsgId; 

            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    dispatch({ type: 'COMPLETE_ASSISTANT_MESSAGE', payload: { id: assistantMessageIdForThisStream } });
                    break; 
                }
                buffer += decoder.decode(value, { stream: true });

                let boundaryIndex;
                while ((boundaryIndex = buffer.indexOf('\n\n')) !== -1 || (boundaryIndex = buffer.indexOf('\r\n\r\n')) !== -1) {
                    const messageEndIndex = boundaryIndex + (buffer.substring(boundaryIndex).startsWith('\r\n\r\n') ? 4 : 2);
                    const messageBlock = buffer.substring(0, boundaryIndex).trim();
                    buffer = buffer.substring(messageEndIndex);

                    if (messageBlock.startsWith('data: ')) {
                        try {
                            const jsonData = messageBlock.substring(6).trim();
                            if (jsonData && jsonData.toUpperCase() !== '[DONE]') {
                                const parsedData = JSON.parse(jsonData);
                                
                                if (parsedData.event_type === 'RawResponsesStreamEvent' && parsedData.data?.delta) {
                                    // Dispatch APPEND_DELTA directly
                                    dispatch({ type: 'APPEND_DELTA', payload: { id: assistantMessageIdForThisStream, delta: parsedData.data.delta } });
                                } else if (parsedData.event_type === 'AgentUpdatedStreamEvent' && parsedData.data?.agent_name) {
                                    dispatch({ type: 'UPDATE_AGENT_NAME', payload: { id: assistantMessageIdForThisStream, agentName: parsedData.data.agent_name } });
                                } else if (parsedData.event_type === 'ServerError' || parsedData.event_type === 'AgentErrorEvent') {
                                     dispatch({ type: 'SET_ERROR', payload: { errorContent: parsedData.data?.error || 'Unknown backend error' } });
                                 }
                            }
                        } catch (e) {
                            console.error("Failed to parse SSE JSON:", e, messageBlock.substring(6));
                        }
                    }
                } 
            } 

        } catch (error: any) {
            console.error("Chat stream error:", error);
             dispatch({ type: 'SET_ERROR', payload: { errorContent: error.message || 'Unknown fetch error' } });
        }

        // After message is inside the DOM, ensure the user bubble is positioned at top of the scroll container
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                if (scrollRef.current) {
                    const el = scrollRef.current.querySelector<HTMLDivElement>(`[data-msg-id="${newUserMessage.id}"]`);
                    if (el) {
                        const containerTop = scrollRef.current.getBoundingClientRect().top;
                        const elTop = el.getBoundingClientRect().top;
                        const delta = elTop - containerTop;
                        scrollRef.current.scrollTop += delta;
                    }
                }
            });
        });
    }, [state.isLoading, state.messageOrder, state.messages, orderedMessages]); // Keep dependencies

    return (
        <div
            className={cn(
                // Remove bottom padding, footer will occupy the space
                "min-h-screen flex flex-col bg-white dark:bg-gray-900 relative", 
                hasStarted ? "justify-start" : "justify-center items-center" 
            )}
        >
            {/* Remove Overlay */}
            {/* <div className="absolute inset-0 bg-black/50 z-0"></div> */}

            {/* Home Link Button */}
            <a 
                href="https://urmstontownjfc.co.uk" 
                target="_blank" // Open in new tab
                rel="noopener noreferrer" // Security best practice for target="_blank"
                title="Urmston Town JFC Home"
                className="fixed top-4 left-4 z-30 p-2 rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                aria-label="Urmston Town JFC Home"
            >
                <Home className="h-5 w-5" />
            </a>

            {/* Main content area */}
            <main
                className={cn(
                    "w-full max-w-3xl mx-auto flex flex-col flex-1 min-h-0", // Keep min-h-0
                    !hasStarted && "items-center justify-center gap-12" 
                )}
            >
                {/* Inner Scroll Container gets ref and scroll handler */} 
                <div 
                    ref={scrollRef} // Ref should be here
                    className={cn(
                        "w-full min-h-0", // Keep min-h-0
                        hasStarted 
                            ? "flex-1 overflow-y-auto scroll-smooth pt-4 pb-32 gap-3" // Keep overflow and padding here
                            : "flex flex-col items-center justify-center gap-12" 
                    )}
                >
                    {/* Welcome Text */} 
                    {!hasStarted && (
                        <h1 className="text-2xl font-medium text-center text-gray-700 dark:text-gray-300"> 
                            Welcome to Urmston Town Juniors FC<br />What can I help you with today?
                        </h1>
                    )}

                    {/* Message list OR initial Input */} 
                    {hasStarted ? (
                        <>
                            <ChatMessages 
                                messages={orderedMessages} 
                                isLoading={isLoading} 
                                loadingMessageId={loadingMessageId}
                            />

                            {/* Sentinel element for Intersection Observer */} 
                            <div ref={endOfMessagesRef} style={{ height: '1px' }} /> 
                        </>
                    ) : (
                        <ChatInput
                            sticky={false} 
                            onSendMessage={handleSendMessage} 
                            onReset={handleReset}
                            isLoading={isLoading} 
                        />
                    )}
                </div>
            </main>

            {/* Gradient Overlay - Positioned after main content (z-20) */}
            {hasStarted && (
                <div className="pointer-events-none fixed bottom-0 inset-x-0 h-28 bg-gradient-to-t from-white via-white/80 to-transparent dark:from-gray-900 dark:via-gray-900/80 dark:to-transparent z-20" /> 
            )}

            {/* Scroll to bottom button (z-30) - Conditionally render based on isAtBottom */}
            {hasStarted && !isAtBottom && (
                <button 
                    onClick={scrollToBottom}
                    className="absolute bottom-20 left-1/2 -translate-x-1/2 z-30 p-2 rounded-full bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 shadow-md hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors"
                    aria-label="Scroll to bottom"
                >
                    <ChevronDown className="h-5 w-5 text-gray-600 dark:text-gray-300" />
                </button>
            )}

            {/* Sticky Input area (z-40) */}
            {hasStarted && (
                <div className="relative z-40"> 
                    <ChatInput
                        sticky={true} 
                        onSendMessage={handleSendMessage} 
                        onReset={handleReset}
                        isLoading={isLoading} 
                    />
                </div>
            )}
        </div>
    );
} 