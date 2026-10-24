// A turn ticket prevents paused, cleared or superseded replies from reappearing.
export class Conversation {
  constructor() { this.version = 0; this.messages = []; this.pending = null; this.lastResult = null; this.reviews = new Map(); }
  begin(content) {
    if (this.pending) throw new Error('A reply is already pending');
    const ticket = ++this.version;
    this.messages.push({ role: 'user', content, message_id: `u:${ticket}`, status: 'pending', ticket });
    this.pending = ticket;
    return ticket;
  }
  finish(ticket, result) {
    if (ticket !== this.version || this.pending !== ticket) return false;
    this.messages.find(m => m.ticket === ticket).status = 'sent';
    this.messages.push({ role: 'assistant', content: result.reply, mode: result.mode, strategy: result.strategy, ticket, result: structuredClone(result) });
    this.lastResult = result; this.pending = null;
    return true;
  }
  fail(ticket) {
    if (ticket !== this.version || this.pending !== ticket) return false;
    this.messages.find(m => m.ticket === ticket).status = 'failed';
    this.pending = null; return true;
  }
  pause() {
    if (this.pending !== null) this.messages.find(m => m.ticket === this.pending).status = 'paused';
    this.pending = null; this.version++;
  }
  clear() { this.pause(); this.messages = []; this.lastResult = null; this.reviews.clear(); }
  review(target, action, value, ticket = this.version) {
    if (this.pending !== null || ticket !== this.version || !this.lastResult?.review_targets?.some(t =>
      t.source_message_id === target.source_message_id && t.field === target.field && t.source_digest === target.source_digest && t.source_text === target.source_text)) return false;
    const key = `${target.field}:${target.source_message_id || target.source_digest}`, previous = this.reviews.get(key);
    const nextValue = action === 'revoke' ? target.value : value;
    if (previous?.action === action && (action === 'revoke' || previous.value === nextValue)) return true;
    if (!previous && this.reviews.size >= 24) return false;
    this.reviews.set(key, {...structuredClone(target), action, value: nextValue,
      revision: Math.max(previous?.revision || 0, target.revision || 0) + 1});
    return true;
  }
  reviewsFor(history, current) {
    const sources = new Set([...history.filter(m => m.role === 'user').map(m => m.content), current]);
    const ids = new Set([...history.filter(m => m.role === 'user').map(m => m.message_id), `u:${this.version}`]);
    // Prune when context expires, never persist review data outside this instance.
    for (const [key, entry] of this.reviews) if (!sources.has(entry.source_text) || (entry.source_message_id && !ids.has(entry.source_message_id))) this.reviews.delete(key);
    return [...this.reviews.values()].map(entry => structuredClone(entry));
  }
  context() {
    const pairs = [];
    for (let i = 0; i < this.messages.length - 1; i++) {
      const user = this.messages[i], reply = this.messages[i+1];
      if (user.role === 'user' && user.status === 'sent' && reply.role === 'assistant' && user.ticket === reply.ticket)
        pairs.push([user,reply].map(({role,content,message_id}) => ({role,content,...(message_id ? {message_id} : {})})));
    }
    const recent = pairs.slice(-10);
    while (recent.flat().reduce((sum, m) => sum + m.content.length, 0) > 16000) recent.shift();
    return recent.flat();
  }
}
