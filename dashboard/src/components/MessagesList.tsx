import type { PoppedMessage } from '../types/queue';
import { MessageItem } from './MessageItem';

interface MessagesListProps {
  messages: PoppedMessage[];
  onAcknowledge: (lockId: string, index: number) => void;
  onDeadLetter: (lockId: string, index: number) => void;
}

export const MessagesList = ({ messages, onAcknowledge, onDeadLetter }: MessagesListProps) => {
  return (
    <div className="card">
      <h3>Popped Messages ({messages.length})</h3>
      {messages.length === 0 ? (
        <p style={{ fontSize: '0.9em', color: '#666', fontStyle: 'italic' }}>
          No messages popped yet
        </p>
      ) : (
        messages.map((msg, index) => (
          <MessageItem
            key={index}
            message={msg}
            onAcknowledge={() => msg.lockId && onAcknowledge(msg.lockId, index)}
            onDeadLetter={() => msg.lockId && onDeadLetter(msg.lockId, index)}
          />
        ))
      )}
    </div>
  );
};
