'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';

// Define the structure of a message object
interface Message {
  id: string;
  role: 'user' | 'assistant'; // Or add 'system', 'tool' as needed
  content: string;
  agentName?: string; // Optional: To display which agent is speaking
}

// Structure matching backend ChatMessageInput Pydantic model
interface ChatMessageInput {
  role: string;
  content: string;
}

// Structure matching backend ChatRequest Pydantic model
interface ChatRequest {
  user_message: string;
  history: ChatMessageInput[];
  session_id?: string | null;
  last_agent_name?: string | null;
}

// Placeholder for the actual SSE event data structure from backend
interface SseEventData {
  event_type: string;
  data: any;
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [lastAgentName, setLastAgentName] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const currentAssistantMessageIdRef = useRef<string | null>(null);

  // --- Cleanup on Unmount --- 
  useEffect(() => {
    // Return cleanup function
    return () => {
      console.log("ChatInterface unmounting - Aborting fetch stream if active");
      abortControllerRef.current?.abort(); // Abort ongoing fetch stream
    };
  }, []);

  // --- Scroll to bottom --- 
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // --- Function to Process Stream Chunks --- 
  const processStreamChunk = useCallback((buffer: string, currentAssistantMessageIdRef: React.MutableRefObject<string | null>): string => {
    let remainingBuffer = buffer;

    // Helper function defined inside useCallback to access state/refs correctly
    const getOrCreateTargetMessage = (messages: Message[]): [Message, number] => {
        let targetMessageIndex = -1;
        if (currentAssistantMessageIdRef.current) {
            targetMessageIndex = messages.findIndex(msg => msg.id === currentAssistantMessageIdRef.current && msg.role === 'assistant');
        }
        if (targetMessageIndex !== -1) {
            return [messages[targetMessageIndex], targetMessageIndex];
        } else {
            const newMsgId = `assistant-${Date.now()}-${Math.random().toString(16).slice(2)}`;
            const newMsg: Message = {
                id: newMsgId,
                role: 'assistant',
                content: '',
                agentName: lastAgentName || 'Assistant'
            };
            currentAssistantMessageIdRef.current = newMsgId;
            return [newMsg, -1];
        }
    };

    while (true) { // Loop until no more complete delimiters are found
        // Find the first occurrence of either delimiter
        const newlineIndex = remainingBuffer.indexOf('\n\n');
        const crlfIndex = remainingBuffer.indexOf('\r\n\r\n');
        let boundaryIndex = -1;
        let delimiterLength = 0;

        if (newlineIndex !== -1 && crlfIndex !== -1) {
            // Both found, take the earlier one
            if (newlineIndex < crlfIndex) {
                 boundaryIndex = newlineIndex;
                 delimiterLength = 2; // \n\n
            } else {
                 boundaryIndex = crlfIndex;
                 delimiterLength = 4; // \r\n\r\n
            }
        } else if (newlineIndex !== -1) {
            boundaryIndex = newlineIndex;
            delimiterLength = 2;
        } else if (crlfIndex !== -1) {
            boundaryIndex = crlfIndex;
            delimiterLength = 4;
        } else {
            // No complete delimiter found in the current buffer
            break; // Exit the while loop
        }

        // Extract and process the message block
        const messageBlock = remainingBuffer.substring(0, boundaryIndex).trim();
        remainingBuffer = remainingBuffer.substring(boundaryIndex + delimiterLength); // Consume message + delimiter

        if (!messageBlock) continue; // Skip empty blocks

        console.log("Processing Block:", JSON.stringify(messageBlock));
        let eventJsonString: string | null = null;
        messageBlock.split('\n').forEach(line => {
            // Trim potential \r from lines ending with \r\n
            const cleanedLine = line.trim();
            if (cleanedLine.startsWith('data:')) {
                eventJsonString = cleanedLine.substring(5).trim();
            }
            // TODO: Handle other SSE fields like 'event:', 'id:', 'retry:' if needed
        });

        if (eventJsonString) {
            try {
                const parsedData: SseEventData = JSON.parse(eventJsonString);
                console.log("SSE event processed:", parsedData);
                setMessages(prevMessages => {
                    let updatedMessages = [...prevMessages];
                    const [targetMessageProto, protoIndex] = getOrCreateTargetMessage(updatedMessages);
                    let targetMessage: Message;
                    let idx: number;
                    if (protoIndex === -1) { // Message needs to be added
                        targetMessage = targetMessageProto;
                        updatedMessages.push(targetMessage);
                        idx = updatedMessages.length - 1;
                    } else { // Message already exists
                        // Create a shallow copy to avoid mutating previous state
                        targetMessage = { ...updatedMessages[protoIndex] }; // <-- Make a copy
                        idx = protoIndex;
                    }

                    // Modify the targetMessage (which is either new or a copy)
                    switch (parsedData.event_type) {
                      case 'RawResponsesStreamEvent':
                        if (parsedData.data?.delta) {
                          console.log(`>>> Processing Delta: '${parsedData.data.delta}' for message ID: ${targetMessage.id}`);
                          const previousContent = targetMessage.content;
                          targetMessage.content += parsedData.data.delta; // Modify copy
                          // updatedMessages[idx] = targetMessage; // Update occurs below
                          console.log(`   Updated content: '${targetMessage.content}' (was: '${previousContent}')`);
                        }
                        break;

                      case 'RunItemStreamEvent':
                      case 'AgentUpdatedStreamEvent':
                        if (parsedData.data?.agent_name) {
                          console.log(`>>> Processing Agent Name: ${parsedData.data.agent_name} for message ID: ${targetMessage.id}`);
                          const previousAgentName = targetMessage.agentName;
                          targetMessage.agentName = parsedData.data.agent_name; // Modify copy
                          // updatedMessages[idx] = targetMessage; // Update occurs below
                          setLastAgentName(parsedData.data.agent_name);
                          console.log(`   Updated agent name: ${targetMessage.agentName} (was: ${previousAgentName})`);
                        }
                        break;

                      case 'FinalOutputEvent':
                         console.log(">>> Processing FinalOutputEvent");
                         setIsLoading(false);
                         console.log("Stream finished (FinalOutputEvent).");
                         currentAssistantMessageIdRef.current = null;
                         // No need to update targetMessage here, just state changes
                         break;

                      case 'ServerError':
                      case 'AgentErrorEvent':
                         console.error(">>> Processing Error Event:", parsedData.data?.error);
                         const errorMsg: Message = {
                             id: `error-${Date.now()}`,
                             role: 'assistant',
                             content: `Backend error: ${parsedData.data?.error || 'Unknown error'}`,
                             agentName: 'System Error'
                         };
                         updatedMessages.push(errorMsg); // Add a new error message
                         setIsLoading(false);
                         currentAssistantMessageIdRef.current = null;
                         // Don't modify targetMessage here
                         break;

                      default:
                        console.warn(">>> Unhandled SSE event type:", parsedData.event_type);
                    }

                    // Place the modified message (new or copy) back into the array
                    // Ensures the update happens correctly after modifications
                    if (idx !== -1 && parsedData.event_type !== 'FinalOutputEvent' && parsedData.event_type !== 'ServerError' && parsedData.event_type !== 'AgentErrorEvent') {
                         updatedMessages[idx] = targetMessage;
                    }

                    console.log('   >>> setMessages update:', JSON.stringify(updatedMessages.slice(-5)));
                    return updatedMessages;
                });
            } catch (error) {
                console.error("Failed to parse SSE JSON data or update state:", eventJsonString, error);
            }
        } else {
             console.warn("Received message block without 'data:' line:", JSON.stringify(messageBlock));
        }
    } // End while loop for processing buffer

    return remainingBuffer; // Return unprocessed part
  }, [lastAgentName]);

  // --- Form Submission Handler (Updated usage of processStreamChunk) --- 
  const handleSubmit = useCallback(async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!inputValue.trim() || isLoading) return;

    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    currentAssistantMessageIdRef.current = null;

    const userMessageContent = inputValue;
    const currentMessages = messages;

    const newUserMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: userMessageContent,
    };

    setMessages((prevMessages) => [...prevMessages, newUserMessage]);
    setInputValue('');
    setIsLoading(true);

    const historyForBackend: ChatMessageInput[] = currentMessages.map(msg => ({
        role: msg.role,
        content: msg.content,
    }));

    const requestBody: ChatRequest = {
        user_message: userMessageContent,
        history: historyForBackend,
        last_agent_name: lastAgentName,
    };

    console.log("Sending POST request to http://localhost:8000/chat/stream with body:", requestBody);

    try {
      const response = await fetch('http://localhost:8000/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });

      if (!response.ok) {
        // Attempt to read error body if possible
        let errorBody = 'Unknown error';
        try {
            errorBody = await response.text();
        } catch {}
        throw new Error(`HTTP error! status: ${response.status}, body: ${errorBody}`);
      }

      if (!response.body) {
        throw new Error('Response body is null');
      }

      // Process the stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();

        if (value) {
             const decodedChunk = decoder.decode(value, { stream: true });
             console.log("<<< Decoded Chunk:", JSON.stringify(decodedChunk)); // Log raw decoded chunk
             buffer += decodedChunk;
             console.log("--- Current Buffer:", JSON.stringify(buffer.slice(-500))); // Log current buffer (last 500 chars)
             buffer = processStreamChunk(buffer, currentAssistantMessageIdRef);
             console.log("--- Remaining Buffer:", JSON.stringify(buffer.slice(-500))); // Log buffer after processing
        }

        if (done) {
            console.log("Stream finished.");
            // Process any final part left in the buffer
            if (buffer.trim()) {
                console.log("Processing final buffer content:", JSON.stringify(buffer));
                // Call one last time, might contain a complete message block ending without \n\n
                 processStreamChunk(buffer + '\n\n', currentAssistantMessageIdRef);
            }
            setIsLoading(false);
            currentAssistantMessageIdRef.current = null;
            break;
        }
      } // End while loop

    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.log("Fetch aborted.");
      } else {
        console.error("Failed to send message or process stream:", error);
        const errorMessage: Message = {
            id: `error-${Date.now()}`,
            role: 'assistant',
            content: `Error: ${error instanceof Error ? error.message : String(error)}`,
            agentName: "System Error"
        };
        setMessages(prev => [...prev, errorMessage]);
      }
       setIsLoading(false);
       currentAssistantMessageIdRef.current = null;
    } finally {
      abortControllerRef.current = null;
    }

  }, [inputValue, isLoading, messages, lastAgentName, processStreamChunk]);

  // --- Input Change Handler --- 
  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(event.target.value);
  };

  return (
    <div className="flex h-full flex-col">
      {/* Message Display Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <p className="text-center text-gray-500 dark:text-gray-400">Start the conversation!</p>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-xs lg:max-w-md rounded-lg px-4 py-2 text-white ${msg.role === 'user' ? 'bg-blue-600' : 'bg-gray-700'}`}>
                {msg.agentName && <p className="text-xs font-semibold mb-1 text-gray-300">{msg.agentName}</p>}
                {/* Replace newline characters with <br /> tags for display */}
                {msg.content.split('\n').map((line, index, arr) => (
                  <React.Fragment key={index}>{line}{index !== arr.length - 1 && <br />}</React.Fragment>
                ))}
              </div>
            </div>
          ))
        )}
        {/* Loading indicator */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-700 rounded-lg px-4 py-2 text-white animate-pulse">
                Thinking...
            </div>
          </div>
        )}
        {/* Ref for scrolling */}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="border-t p-4 bg-white dark:bg-gray-800">
        <form onSubmit={handleSubmit} className="flex items-center space-x-2">
          <input
            type="text"
            placeholder="Type your message..."
            value={inputValue}
            onChange={handleInputChange}
            disabled={isLoading}
            className="flex-1 rounded-md border border-gray-300 p-2 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={isLoading || !inputValue.trim()}
            className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed">
            Send
          </button>
        </form>
      </div>
    </div>
  );
} 