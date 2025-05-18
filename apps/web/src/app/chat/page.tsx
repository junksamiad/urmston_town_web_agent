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
    | { type: 'UPDATE_ASSISTANT_JSON_CONTENT'; payload: { id: string; agentResponseText: string; overallTaskComplete: boolean; passOffToAgent: string | null } }
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
        
        case 'UPDATE_ASSISTANT_JSON_CONTENT':
            if (!state.messages[action.payload.id]) return state;
            const msgToUpdate = state.messages[action.payload.id];
            return {
                ...state,
                messages: {
                    ...state.messages,
                    [action.payload.id]: {
                        ...msgToUpdate,
                        content: action.payload.agentResponseText,
                    }
                },
            };

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
            if (state.loadingMessageId !== action.payload.id && state.currentAssistantMessageId !== action.payload.id) return state;
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
    const { messages, messageOrder, isLoading, loadingMessageId, currentAssistantMessageId } = state;
    const orderedMessages = useMemo(() => 
        messageOrder.map(id => messages[id]).filter(Boolean)
    , [messageOrder, messages]);
    const hasStarted = state.messageOrder.length > 0;

    const currentAssistantJsonBuffer = useRef<string>("");

    // Ref for the scrollable message container
    const scrollRef = useRef<HTMLDivElement>(null);
    // Ref for the sentinel element at the end of messages
    const endOfMessagesRef = useRef<HTMLDivElement>(null);
    // State to track if scroll is at the bottom
    const [isAtBottom, setIsAtBottom] = useState(true);
    
    const userJustSentRef = useRef(false); 
    const lastUserSend = useRef<number>(0);

    // Helper to scroll the sentinel into view (guaranteed to exist when chat has started)
    const scrollMessagesToBottom = useCallback((smooth: boolean = true) => {
        if (endOfMessagesRef.current) {
            endOfMessagesRef.current.scrollIntoView({
                behavior: smooth ? 'smooth' : 'auto',
                block: 'start',
            });
        } else if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, []);

    // Scroll to bottom effect (keep as is for now, depends on loadingMessageId)
    useEffect(() => {
        if (Date.now() - lastUserSend.current < 300) return;
        // Note: This still scrolls based on loadingMessageId, which might need adjustment
        // if we want it purely based on the IntersectionObserver state later.
        if (scrollRef.current && loadingMessageId) { 
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [orderedMessages.length, loadingMessageId]);

    // Scroll listener to compute whether we're at bottom
    useEffect(() => {
        const el = scrollRef.current;
        if (!hasStarted || !el) return;

        const handleScroll = () => {
            const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
            setIsAtBottom(atBottom);
        };

        // Fire once for initial state
        handleScroll();
        el.addEventListener('scroll', handleScroll);

        return () => {
            el.removeEventListener('scroll', handleScroll);
        };
    }, [hasStarted]);

    // Auto-scroll after every new message
    useEffect(() => {
        // Keep view pinned to bottom while assistant streaming, unless user scrolled up.
        if (!userJustSentRef.current && isAtBottom) {
            scrollMessagesToBottom(false);
        }
        // reset signal
        if (userJustSentRef.current) userJustSentRef.current = false;
    }, [messageOrder, isAtBottom, scrollMessagesToBottom]);

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

    // Main useEffect for handling SSE (Still consider if this is needed if handleSendMessage processes the stream)
    useEffect(() => {
        if (!hasStarted) {
            // console.log("Chat not started, SSE connection deferred."); // Removed this log
            return;
        }
        // console.log("SSE useEffect triggered. Potential EventSource connection.");
        // const eventSource = new EventSource('http://localhost:8000/chat/stream');
        // eventSource.onopen = () => console.log("SSE connection opened via useEffect.");
        // eventSource.onmessage = (event) => { /* ... SSE processing ... */ };
        // eventSource.onerror = (err) => { /* ... */ };
        // return () => eventSource.close();
        // For now, this useEffect will be a NO-OP as handleSendMessage is processing the stream.
        // If you decide to switch to EventSource as primary, uncomment and adapt the above.
        return () => {}; // No-op cleanup

    }, [hasStarted, currentAssistantMessageId]); // Dependencies kept for potential future use with EventSource

    const handleSendMessage = useCallback(async (userInput: string) => {
        if (isLoading) return;

        const newUserMessage: Message = {
            id: `user-${Date.now()}`,
            role: 'user',
            content: userInput,
        };
        dispatch({ type: 'ADD_USER_MESSAGE', payload: newUserMessage });
        userJustSentRef.current = true;
        lastUserSend.current = Date.now();
        requestAnimationFrame(() => { scrollMessagesToBottom(true); });

        // Removed unused newAssistantMsgId

        const historyForBackend: ChatMessageInput[] = orderedMessages.map(msg => ({
            role: msg.role,
            content: msg.content,
        }));

        const requestBodyData = {
             user_message: userInput,
             history: historyForBackend,
             last_agent_name: orderedMessages.length > 0 && orderedMessages[orderedMessages.length-1].role === 'assistant' ? orderedMessages[orderedMessages.length-1].agentName : null,
             session_id: localStorage.getItem('session_id') || undefined,
         };

        try {
            const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
            const response = await fetch(`${apiUrl}/chat/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                },
                body: JSON.stringify(requestBodyData),
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            if (!response.body) throw new Error("Response body is null");

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fetchBuffer = '';
            let activeMessageId = ""; 

            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    if(activeMessageId) {
                        dispatch({ type: 'COMPLETE_ASSISTANT_MESSAGE', payload: { id: activeMessageId } });
                    }
                    break; 
                }
                fetchBuffer += decoder.decode(value, { stream: true });

                let boundaryIdx;
                while ((boundaryIdx = fetchBuffer.indexOf('\n\n')) !== -1 || (boundaryIdx = fetchBuffer.indexOf('\r\n\r\n')) !== -1) {
                    const messageEndIdx = boundaryIdx + (fetchBuffer.substring(boundaryIdx).startsWith('\r\n\r\n') ? 4 : 2);
                    const rawEventData = fetchBuffer.substring(0, boundaryIdx).trim();
                    fetchBuffer = fetchBuffer.substring(messageEndIdx);

                    if (rawEventData.startsWith('data: ')) {
                        const jsonDataString = rawEventData.substring(5).trim();
                        console.log("Attempting to parse JSON from SSE data line:", jsonDataString);
                        if (jsonDataString && jsonDataString.toUpperCase() !== '[DONE]') {
                            try {
                                const parsedEvent = JSON.parse(jsonDataString);
                                if (parsedEvent.event_type === 'START_ASSISTANT_MESSAGE') {
                                    activeMessageId = parsedEvent.data.id;
                                    currentAssistantJsonBuffer.current = ""; 
                                    dispatch({ type: 'START_ASSISTANT_MESSAGE', payload: { id: parsedEvent.data.id, agentName: parsedEvent.data.agent_name || 'Assistant' } });
                                } else if (parsedEvent.event_type === 'RawResponsesStreamEvent' && parsedEvent.data?.delta) {
                                    if (activeMessageId) {
                                        currentAssistantJsonBuffer.current += parsedEvent.data.delta;
                                        // Attempt to parse the buffer and update content if agent_response_text is available
                                        try {
                                            const parsedBuffer = JSON.parse(currentAssistantJsonBuffer.current);
                                            if (parsedBuffer.agent_response_text !== undefined) {
                                                dispatch({
                                                    type: 'UPDATE_ASSISTANT_JSON_CONTENT',
                                                    payload: {
                                                        id: activeMessageId,
                                                        agentResponseText: parsedBuffer.agent_response_text,
                                                        overallTaskComplete: parsedBuffer.overall_task_complete || false, 
                                                        passOffToAgent: parsedBuffer.pass_off_to_agent || null
                                                    }
                                                });
                                            }
                                        // eslint-disable-next-line @typescript-eslint/no-unused-vars
                                        } catch (_e) {
                                            // console.log("Incremental parse failed, waiting for more chunks:", _e); // Optional: for debugging
                                            // Intentionally ignore parsing errors for incomplete JSON, wait for more chunks
                                        }
                                    }
                                } else if (parsedEvent.event_type === 'AgentUpdatedStreamEvent' && parsedEvent.data?.agent_name) {
                                    if (activeMessageId) {
                                        dispatch({ type: 'UPDATE_AGENT_NAME', payload: { id: activeMessageId, agentName: parsedEvent.data.agent_name } });
                                    }
                                } else if (parsedEvent.event_type === 'COMPLETE_ASSISTANT_MESSAGE') {
                                    if (activeMessageId && activeMessageId === parsedEvent.data.id) { 
                                        let finalContent = currentAssistantJsonBuffer.current;
                                        try {
                                            const structuredResp = JSON.parse(currentAssistantJsonBuffer.current);
                                            if (structuredResp.agent_response_text !== undefined) {
                                                finalContent = structuredResp.agent_response_text;
                                                dispatch({ 
                                                    type: 'UPDATE_ASSISTANT_JSON_CONTENT', 
                                                    payload: { 
                                                        id: activeMessageId, 
                                                        agentResponseText: finalContent,
                                                        overallTaskComplete: structuredResp.overall_task_complete || false,
                                                        passOffToAgent: structuredResp.pass_off_to_agent || null
                                                    }
                                                });
                                            } else {
                                                console.warn("COMPLETE_ASSISTANT_MESSAGE: Parsed JSON, but no agent_response_text. Raw deltas remain.");
                                            }
                                        } catch (parseError) { 
                                            console.warn("Final JSON parse failed on complete in fetch stream. Content remains raw deltas. Error:", parseError);
                                        }
                                        
                                        dispatch({ type: 'COMPLETE_ASSISTANT_MESSAGE', payload: { id: parsedEvent.data.id } });
                                        currentAssistantJsonBuffer.current = "";
                                        activeMessageId = ""; 
                                    }
                                } else if (parsedEvent.event_type === 'code_validation_result') {
                                    console.log("Received code_validation_result:", parsedEvent.data); 

                                    if (activeMessageId) { 
                                        let valText = "Code validation result received."; // Default text
                                        if (parsedEvent.data?.status === 'invalid' && parsedEvent.data?.display_message) {
                                            valText = parsedEvent.data.display_message;
                                        } else if (parsedEvent.data?.status === 'valid') {
                                            // This path should no longer be hit if backend suppresses valid code messages
                                            // but keeping it as a fallback or for future use if that changes.
                                            valText = `Code: ${parsedEvent.data.raw_code} - Status: ${parsedEvent.data.status}.`;
                                            if (parsedEvent.data.details) {
                                                valText += ` Type: ${parsedEvent.data.details.code_type}, Team: ${parsedEvent.data.details.team_name}, Age: u${parsedEvent.data.details.age_group}, Season: ${parsedEvent.data.details.season_start_year}-${parsedEvent.data.details.season_end_year}.`;
                                            }
                                        } else if (parsedEvent.data?.status === 'invalid' && parsedEvent.data?.reason) {
                                            // Fallback if display_message is not there but reason is
                                            valText = `Code: ${parsedEvent.data.raw_code} - Status: invalid. Reason: ${parsedEvent.data.reason}.`;
                                        }

                                        console.log("Dispatching UPDATE_ASSISTANT_JSON_CONTENT for validation using activeMessageId", { activeMessageId, valText }); 
                                        dispatch({ 
                                            type: 'UPDATE_ASSISTANT_JSON_CONTENT', 
                                            payload: { 
                                                id: activeMessageId, // USE THE CURRENT activeMessageId
                                                agentResponseText: valText, 
                                                overallTaskComplete: true, // Assuming validation is a 'complete' task in itself
                                                passOffToAgent: null 
                                            } 
                                        });
                                        // The COMPLETE_ASSISTANT_MESSAGE for this validation sequence is sent separately by the backend
                                        // and will be handled by the 'COMPLETE_ASSISTANT_MESSAGE' event case using its own ID.
                                    } else {
                                        console.warn("code_validation_result received but no activeMessageId was set. This indicates the preceding START_ASSISTANT_MESSAGE for validation was missed or cleared prematurely.");
                                    }
                                } else if (parsedEvent.event_type === 'ServerError' || parsedEvent.event_type === 'AgentErrorEvent') {
                                     dispatch({ type: 'SET_ERROR', payload: { errorContent: parsedEvent.data?.error || 'Unknown backend error' } });
                                     if(activeMessageId) dispatch({ type: 'COMPLETE_ASSISTANT_MESSAGE', payload: { id: activeMessageId } });
                                     break; 
                                 }
                            } catch (jsonParseError) {
                                console.error(
                                    "Failed to parse SSE JSON from fetch stream:", 
                                    jsonParseError, 
                                    "\nOriginal rawEventData line was:", rawEventData, 
                                    "\nString attempted to parse (jsonDataString) was:", jsonDataString
                                );
                            }
                        }
                    }
                } 
            } 
        } catch (fetchError: unknown) {
            console.error("Chat stream fetch error:", fetchError);
            const errMsg = fetchError instanceof Error ? fetchError.message : 'Unknown fetch error';
             dispatch({ type: 'SET_ERROR', payload: { errorContent: errMsg } });
        }
    }, [isLoading, orderedMessages, dispatch, scrollMessagesToBottom]); // Added scrollMessagesToBottom

    console.log("ChatPage render state:", { messages, messageOrder, isLoading, currentAssistantMessageId, hasStarted }); // Added log
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
                            Welcome to the for Urmston Town Juniors FC Registration Portal.<br />Please enter your registration code below to begin.
                        </h1>
                    )}

                    {/* Message list OR initial Input */} 
                    {hasStarted ? (
                        <>
                            <ChatMessages 
                                messages={orderedMessages} 
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