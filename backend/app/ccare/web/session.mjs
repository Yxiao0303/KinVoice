// A turn ticket prevents paused, cleared or superseded replies from reappearing.
export class Conversation {
  constructor() { this.version = 0; this.messages = []; this.pending = null; this.lastResult = null; }
  begin(content) {
    if (this.pending) throw new Error('A reply is already pending');
    const ticket = ++this.version;
    this.messages.push({ role: 'user', content, status: 'pending', ticket });
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
  clear() { this.pause(); this.messages = []; this.lastResult = null; }
  context() {
    const pairs = [];
    for (let i = 0; i < this.messages.length - 1; i++) {
      const user = this.messages[i], reply = this.messages[i+1];
      if (user.role === 'user' && user.status === 'sent' && reply.role === 'assistant' && user.ticket === reply.ticket)
        pairs.push([user,reply].map(({role,content}) => ({role,content})));
    }
    const recent = pairs.slice(-10);
    while (recent.flat().reduce((sum, m) => sum + m.content.length, 0) > 16000) recent.shift();
    return recent.flat();
  }
}
