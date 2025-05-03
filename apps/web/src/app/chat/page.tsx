import React from 'react';
import ChatInterface from '@/app/chat/_components/chat-interface'; // Import the client component

// The main page remains a Server Component, but it renders the Client Component
// that handles the interactive chat logic.
export default function ChatPage() {
  return (
    <div className="h-screen bg-gray-100 dark:bg-gray-900">
      {/* Render the client-side chat interface */}
      <ChatInterface />
    </div>
  );
} 