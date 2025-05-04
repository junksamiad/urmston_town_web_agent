import React from 'react';
import { cn } from '@/lib/utils';
import { Clipboard } from 'lucide-react';

interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    agentName?: string;
    isLoading?: boolean;
}

interface MessageListProps {
    messages: Message[];
    isLoading: boolean;
    loadingMessageId: string | null;
}

const MessageList: React.FC<MessageListProps> = ({ messages, isLoading, loadingMessageId }) => {

    const copyToClipboard = async (text: string) => {
        try {
            await navigator.clipboard.writeText(text);
            console.log("Copied to clipboard!");
        } catch (err) {
            console.error("Failed to copy text: ", err);
        }
    };

    return (
        <div className="flex-1 space-y-4">
            {messages.map((msg) => (
                <React.Fragment key={msg.id}>
                    {msg.role === 'user' ? (
                        <div className="flex justify-end" data-msg-id={msg.id}>
                            <div
                                className={cn(
                                    "rounded-3xl p-3 prose prose-sm dark:prose-invert break-words max-w-[75%] shadow-sm",
                                    'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100'
                                )}
                            >
                                {msg.content}
                            </div>
                        </div>
                    ) : (
                        <div className="flex flex-col items-start" data-msg-id={msg.id} key={`assist-grp-${msg.id}`}>
                            <div
                                className={cn(
                                    "rounded-lg p-3 prose prose-sm dark:prose-invert break-words w-auto",
                                    'text-gray-900 dark:text-gray-100'
                                )}
                            >
                                {msg.isLoading && !msg.content ? (
                                    <span className="animate-pulse text-gray-500 dark:text-gray-400">Assistant thinking...</span>
                                ) : (
                                    <>
                                        {/* Split content by newline and render with <br /> */}
                                        {msg.content.split('\n').map((line, index, arr) => (
                                            <React.Fragment key={index}>
                                                {line}
                                                {index < arr.length - 1 && <br />}
                                            </React.Fragment>
                                        ))}
                                        {/* Pulsing cursor only shown when loading and content exists */}
                                        {loadingMessageId === msg.id && msg.content && <span className="animate-pulse animate-fade-in ml-1">▍</span>}
                                    </>
                                )}
                            </div>
                            {!msg.isLoading && msg.content && (
                                <button
                                    onClick={() => copyToClipboard(msg.content)}
                                    className="p-1 mt-1 pl-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 rounded-md"
                                    aria-label="Copy message"
                                    title="Copy message"
                                >
                                    <Clipboard className="h-4 w-4" />
                                </button>
                            )}
                        </div>
                    )}
                </React.Fragment>
            ))}
        </div>
    );
};

export default MessageList; 