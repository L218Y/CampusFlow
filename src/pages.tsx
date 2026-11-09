import { ArrowRight, Check, FolderOpen, RotateCcw, Sparkles, WandSparkles } from 'lucide-react';
import type { Health, Plan, Task } from './lib';

export function ProjectList({ tasks, plans, onPlan, onTask, onStart }: {
  tasks: Task[]; plans: Plan[]; onPlan: (p: Plan) => void; onTask: (t: Task) => void; onStart: () => void;
}) {
  const groups = new Map<string, Task[]>();
  for (const task of tasks) {
    if (!task.project_id) continue;
    groups.set(task.project_id, [...(groups.get(task.project_id) || []), task]);
  }
  const drafts = plans.filter(p => p.status === 'pending');
  return <>
    <div className="page-heading"><div><span className="eyebrow">CAMPUSFLOW / PROJECTS</span><h1>项目计划</h1><p>把学习目标拆成可完成的步骤。</p></div><button className="button primary" onClick={onStart}><Sparkles size={17}/>AI 制定计划</button></div>
    {drafts.length > 0 && <section><div className="section-heading flush"><h2>待确认的计划草稿</h2></div><div className="project-grid">{drafts.map(plan => <article className="project-card draft" key={plan.id}><span className="pill">AI 草稿</span><h3>{plan.title}</h3><p>{plan.goal}</p><small>{plan.tasks.length} 个步骤 · 每天 {plan.daily_budget_minutes} 分钟</small><button className="button secondary" onClick={() => onPlan(plan)}>调整并保存 <ArrowRight size={15}/></button></article>)}</div></section>}
    <div className="section-heading flush"><h2>已保存的项目</h2><span className="muted">{groups.size} 个项目</span></div>
    {groups.size ? <div className="project-grid">{[...groups.entries()].map(([id, entries]) => {
      const finished = entries.filter(t => t.status === 'done').length;
      const rate = Math.round(finished / entries.length * 100);
      return <article className="project-card" key={id}><div className="empty-icon"><FolderOpen size={22}/></div><h3>{entries[0].project_title || '学习计划'}</h3><div className="progress-label"><span>{finished} / {entries.length} 步已完成</span><strong>{rate}%</strong></div><div className="mini-progress"><span style={{ width: rate + '%' }}/></div><div className="project-task-list">{[...entries].sort((a,b) => (a.step_index ?? a.id) - (b.step_index ?? b.id)).map(t => <button key={t.id} onClick={() => onTask(t)}>{t.status === 'done' ? <Check size={14}/> : <i/>}{t.title}</button>)}</div></article>;
    })}</div> : <section className="panel"><div className="empty-state"><div className="empty-icon"><FolderOpen size={25}/></div><h3>还没有已保存的项目</h3><p>可以让 AI 先起草计划，再检查步骤和时间。</p><div className="empty-actions"><button className="button primary" onClick={onStart}><Sparkles size={15}/>开始规划</button></div></div></section>}
  </>;
}

export function Settings({ health, tasks, seedBusy, onRefresh, onSeed }: {
  health: Health; tasks: Task[]; seedBusy: boolean; onRefresh: () => Promise<void>; onSeed: () => void;
}) {
  return <>
    <div className="page-heading"><div><span className="eyebrow">CAMPUSFLOW / SETTINGS</span><h1>工作区设置</h1><p>管理模型连接和本地数据。</p></div></div>
    <section className="panel settings-panel">
      <div className="section-heading"><h2><Sparkles size={18}/>大模型 API</h2><span className={'pill ' + (health.configured ? '' : 'waiting')}>{health.configured ? '密钥已配置' : '待配置'}</span></div>
      <div className="settings-row"><span>服务提供商</span><strong>{health.provider}</strong></div>
      <div className="settings-row"><span>模型</span><code>{health.model}</code></div>
      <div className="setup-instructions">
        <strong>连接 DeepSeek API</strong>
        <ol><li>在项目目录将 <code>.env.example</code> 复制为 <code>.env</code>。</li><li>在文件中填写 <code>DEEPSEEK_API_KEY</code>。</li><li>重启本地服务，发送一条消息验证连通性。</li></ol>
        <p>密钥只由后端读取。AI 对话及所需任务信息会发送给模型服务。</p>
      </div>
      <button className="button secondary" onClick={onRefresh}><RotateCcw size={14}/>刷新配置状态</button>
    </section>
    <section className="panel settings-panel">
      <div className="section-heading"><h2><FolderOpen size={18}/>本地数据</h2><span className="pill">SQLite</span></div>
      <div className="settings-row"><span>数据文件</span><code>data/campusflow.db</code></div>
      <div className="settings-row"><span>应用时区</span><strong>北京时间</strong></div>
      <button className="button secondary" disabled={!!tasks.length || seedBusy} onClick={onSeed}><WandSparkles size={16}/>导入演示示例</button>
      <p className="muted settings-note">空工作区可导入一组课堂演示任务。</p>
    </section>
  </>;
}
