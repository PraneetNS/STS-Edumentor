/**
 * Sidebar — Chat history navigation panel.
 * Collapsed by default, opens smoothly as an overlay.
 */
import React, { memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, MessageSquare, Trash2, User, Settings, BookOpen, X } from 'lucide-react';

const GROUP_LABELS = {
  today:     'Today',
  yesterday: 'Yesterday',
  previous:  'Previous',
};

function ChatItem({ conv, isActive, onSelect, onDelete }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -10 }}
      className={`chat-item ${isActive ? 'active' : ''}`}
      onClick={() => onSelect(conv.id)}
      role="button"
      tabIndex={0}
    >
      <div className="chat-item-icon"><MessageSquare size={14} /></div>
      <span className="chat-item-title">{conv.title}</span>
      <button
        className="chat-delete-btn"
        onClick={e => onDelete(conv.id, e)}
        aria-label="Delete"
      >
        <Trash2 size={13} />
      </button>
    </motion.div>
  );
}

export const Sidebar = memo(function Sidebar({
  grouped,
  activeId,
  onSelect,
  onDelete,
  onNewChat,
  isOpen,
  onClose,
}) {
  return (
    <>
      {/* Overlay covers the whole screen when open */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            className="sidebar-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
        )}
      </AnimatePresence>

      <aside className={`sidebar ${isOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <div className="sidebar-brand-icon" style={{ background: 'transparent', boxShadow: 'none', padding: 0 }}>
              <img src="/mascot.png" alt="Logo" style={{ width: '100%', height: '100%', objectFit: 'contain', mixBlendMode: 'multiply' }} />
            </div>
            <div>
              <div className="sidebar-brand-name">EduMentor</div>
              <div className="sidebar-brand-sub">Workspace</div>
            </div>
            <button className="sidebar-close-btn" onClick={onClose}>
              <X size={16} />
            </button>
          </div>

          <button className="new-session-btn" onClick={onNewChat}>
            <Plus size={15} />
            <span>New Session</span>
          </button>
        </div>

        <div className="sidebar-scroll">
          {['today', 'yesterday', 'previous'].map(group => {
            const items = grouped[group];
            if (!items?.length) return null;
            return (
              <div className="sidebar-section" key={group}>
                <div className="sidebar-section-label">{GROUP_LABELS[group]}</div>
                <AnimatePresence>
                  {items.map(conv => (
                    <ChatItem
                      key={conv.id}
                      conv={conv}
                      isActive={conv.id === activeId}
                      onSelect={id => { onSelect(id); onClose(); }}
                      onDelete={onDelete}
                    />
                  ))}
                </AnimatePresence>
              </div>
            );
          })}

          {!grouped.today?.length && !grouped.yesterday?.length && !grouped.previous?.length && (
            <div className="p-6 text-center text-slate-500 text-xs">
              No previous sessions
            </div>
          )}
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-footer-item">
            <User size={15} /> <span>Student Profile</span>
          </div>
          <div className="sidebar-footer-item">
            <BookOpen size={15} /> <span>Learning Progress</span>
          </div>
          <div className="sidebar-footer-item">
            <Settings size={15} /> <span>Settings</span>
          </div>
        </div>
      </aside>
    </>
  );
});
