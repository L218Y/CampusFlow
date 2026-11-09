import { useEffect, useRef, useState } from 'react';
import {
  ArrowRight, BookOpen, CalendarDays, Check, ChevronRight, Clock3, LoaderCircle,
  RotateCcw, Send, Sparkles, WandSparkles, X,
} from 'lucide-react';
import { api, LABELS, type Health, type Message, type Plan } from './lib';

const suggestions = [
  [WandSparkles, '帮我拆解一个学习目标', '我想完成一份人工智能课程报告，请先询问截止日期和每日可用时间，再帮我拆解计划。'],
  [CalendarDays, '看看这周有哪些任务', '请查看这周的任务，并按紧急程度给我一些建议。'],
  [Clock3, '帮我安排今天的学习', '请查询我的任务，帮我安排今天的学习。先问我今天还有多少时间。'],
] as const;

export default function Assistant({ health, open, onClose, onSettings, onChanged, onUndo, onPlan, prompt }: {
  health: Health; open: boolean; onClose: () => void; onSettings: () => void;
  onChanged: () => Promise<void>; onUndo: (id: string) => void; onPlan: (p: Plan) => void;
  prompt: { text: string; nonce: number };
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    api<Message[]>('/chat').then(history => {
      if (active) setMessages(history);
    }).catch(() => {});
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (prompt.text) {
      setInput(prompt.text);
      inputRef.current?.focus();
    }
  }, [prompt]);
  useEffect(() => {
    const element = scrollRef.current;
    if (element && messages.length) element.scrollTop = element.scrollHeight;
  }, [messages, busy, open]);

  async function send() {
    const text = input.trim();
    if (!text || busy || !health.configured) return;
    const requestId = crypto.randomUUID();
    setInput('');
    setError('');
    setBusy(true);
    setMessages(previous => [...previous, { id: requestId, role: 'user', content: text }]);
    try {
      const answer = await api<Message>('/chat', 'POST', { message: text, request_id: requestId });
      setMessages(previous => [...previous, answer]);
      await onChanged();
    } catch (failure) {
      setMessages(previous => previous.filter(message => message.id !== requestId));
      setInput(current => current || text);
      setError((failure as Error).message);
      await onChanged();
    } finally { setBusy(false); }
  }
  async function clear() {
    try {
      await api('/chat', 'DELETE');
      setMessages([]);
      setError('');
    } catch (failure) { setError((failure as Error).message); }
  }

  return <aside className={'assistant ' + (open ? 'mobile-open' : '')} aria-label="课伴 AI 助手">
    <div className="assistant-header">
      <div className="assistant-icon"><Sparkles size={20}/></div>
      <div><h2>课伴 AI</h2><span>查询任务，制定和调整学习计划</span></div>
      <button className="icon-button" title="清空对话" aria-label="清空对话" disabled={busy || !messages.length} onClick={clear}><RotateCcw size={16}/></button>
      <button className="icon-button close-assistant" aria-label="关闭 AI 助手" onClick={onClose}><X size={18}/></button>
    </div>
    <div className="ai-status"><span className={health.configured ? 'configured' : ''}/>{health.configured ? '已配置 · ' + health.model : 'API 待配置'}<span className="ai-status-label">学习助手</span></div>
    <div className="chat-scroll" ref={scrollRef}>
      {!messages.length ? <div className="assistant-welcome">
        <div className="welcome-ai-icon"><Sparkles size={28}/></div>
        <h3>今天想完成什么？</h3>
        <p>告诉我你的目标、截止日期或可用时间，<br/>我会帮你安排下一步。</p>
        <div className="prompt-label">可以这样开始</div>
        {suggestions.map(([Icon, label, value]) => <button className="prompt-card" key={label} onClick={() => { setInput(value); inputRef.current?.focus(); }}><Icon size={16}/><span>{label}</span><ChevronRight size={14}/></button>)}
        <div className="assistant-tip"><BookOpen size={15}/><p>计划草稿可以修改，保存后才会进入任务和日历。</p></div>
      </div> : <div className="messages" aria-live="polite">{messages.map(message => <div className={'message ' + message.role} key={message.id}>
        {message.role === 'assistant' && <div className="message-avatar"><Sparkles size={13}/></div>}
        <div className="message-body">
          {message.role === 'assistant' && <span className="message-name">课伴 AI</span>}
          <div className={'message-content ' + (message.error ? 'has-error' : '')}>{message.content}</div>
          {message.traces?.map(trace => <div key={trace.id}>
            {trace.result.draft && <button className="button secondary small-button" onClick={() => onPlan(trace.result.draft!)}>查看计划草稿 <ArrowRight size={13}/></button>}
            <details className={'tool-trace ' + trace.status}>
              <summary>{trace.status === 'success' ? <Check size={12}/> : <X size={12}/>}<span>{LABELS[trace.name] || trace.name}</span><small>{trace.duration_ms} ms</small><ChevronRight size={12}/></summary>
              <div className="trace-content"><code>{trace.name}</code><pre>{JSON.stringify({ arguments: trace.arguments, result: trace.result }, null, 2)}</pre>
                {trace.result.action_id && <button className="text-button" onClick={() => onUndo(trace.result.action_id!)}><RotateCcw size={12}/>撤销此操作</button>}
              </div>
            </details>
          </div>)}
          {!!message.usage?.total_tokens && <span className="token-usage">本轮 {message.usage.total_tokens.toLocaleString()} tokens</span>}
        </div>
      </div>)}</div>}
      {busy && <div className="chat-thinking" role="status"><LoaderCircle className="spin" size={14}/>正在处理你的需求…</div>}
      {error && <div className="chat-error" role="alert">{error}<button className="text-button" onClick={onSettings}>查看 API 设置 <ArrowRight size={12}/></button></div>}
    </div>
    {!health.configured && <div className="api-notice"><span>配置 API 后即可使用 AI 对话与规划。</span><button onClick={onSettings}>去设置 <ArrowRight size={12}/></button></div>}
    <div className="chat-composer">
      <div className="composer-box">
        <textarea ref={inputRef} rows={3} maxLength={3000} aria-label="给课伴发送消息" placeholder="例如：把周五的报告拆成四步…" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); }
        }}/>
        <div className="composer-bottom"><span><Sparkles size={12}/>学习任务助手</span><button className="send-button" disabled={!input.trim() || busy || !health.configured} title={health.configured ? '发送消息' : '请先配置 API Key'} aria-label="发送消息" onClick={send}>{busy ? <LoaderCircle className="spin" size={16}/> : <Send size={16}/>}</button></div>
      </div>
      <p>Enter 发送 · Shift + Enter 换行</p>
    </div>
  </aside>;
}
