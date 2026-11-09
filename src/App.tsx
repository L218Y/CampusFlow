import { useEffect, useState } from 'react';
import {
  ArrowRight, BookOpen, CalendarDays, Check, CheckCheck, ChevronLeft, ChevronRight,
  ClipboardList, Flag, FolderOpen, GraduationCap, LayoutDashboard, ListTodo,
  LoaderCircle, MessageSquare, Plus, Search, Settings2, Sparkles, Trash2, X, Zap,
} from 'lucide-react';
import Assistant from './Assistant';
import { Modal, PlanEditor, TaskEditor, TaskRow } from './components';
import { Settings, ProjectList } from './pages';
import {
  addDays, api, dateTitle, freshTask, monday, shortDate, taskDay, today,
  type Change, type Health, type Overview, type Plan, type Task,
} from './lib';

const pages = [
  ['overview', '今日概览', LayoutDashboard], ['tasks', '我的任务', ListTodo],
  ['calendar', '学习日历', CalendarDays], ['projects', '项目计划', FolderOpen],
  ['settings', '工作区设置', Settings2],
] as const;
type Page = typeof pages[number][0];
const initialStats: Overview = { total: 0, completed: 0, pending: 0, overdue: 0, today: 0, completion_rate: 0 };
const initialHealth: Health = { configured: false, model: 'deepseek-flash', provider: 'DeepSeek' };
const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const byDate = (a: Task, b: Task) => (a.due_date || 'z').localeCompare(b.due_date || 'z');
const onDay = (task: Task, day: string) => taskDay(task) === day || task.due_date === day;

export default function App() {
  const [page, setPage] = useState<Page>('overview');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [stats, setStats] = useState(initialStats);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [health, setHealth] = useState(initialHealth);
  const [loading, setLoading] = useState(true);
  const [serverError, setServerError] = useState('');
  const [search, setSearch] = useState('');
  const [course, setCourse] = useState('');
  const [filter, setFilter] = useState('all');
  const [selectedDay, setSelectedDay] = useState(today);
  const [week, setWeek] = useState(() => monday(today()));
  const [editing, setEditing] = useState<Task | null>(null);
  const [editingPlan, setEditingPlan] = useState<Plan | null>(null);
  const [deleting, setDeleting] = useState<Task | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [seedBusy, setSeedBusy] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [prompt, setPrompt] = useState({ text: '', nonce: 0 });
  const [notice, setNotice] = useState<{ text: string; action?: string; error?: boolean } | null>(null);
  const currentDay = today();
  const days = weekdays.map((_, index) => addDays(week, index));

  async function refresh() {
    try {
      const [newTasks, newStats, newPlans, newHealth] = await Promise.all([
        api<Task[]>('/tasks'), api<Overview>('/overview'), api<Plan[]>('/plans'), api<Health>('/health'),
      ]);
      setTasks(newTasks);
      setStats(newStats);
      setPlans(newPlans);
      setHealth(newHealth);
      setServerError('');
    } catch {
      setServerError('暂时无法读取工作区，请确认本地服务正在运行。');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    if (!notice || notice.action || notice.error) return;
    const timer = window.setTimeout(() => setNotice(null), 4500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const showError = (error: unknown) => setNotice({ text: (error as Error).message, error: true });
  const showChange = (text: string, change: Change) => setNotice({ text, action: change.action_id });
  function navigate(next: Page) {
    setPage(next);
    window.scrollTo({ top: 0 });
  }
  function openSettings() {
    navigate('settings');
    setAssistantOpen(false);
  }
  function startPlan() {
    setPrompt(p => ({ text: '我想制定一个学习计划，请先问我目标、截止日期和每天可用的时间。', nonce: p.nonce + 1 }));
    setAssistantOpen(true);
  }
  function openDraft(draft: Plan) {
    const current = plans.find(p => p.id === draft.id) || draft;
    if (current.status !== 'pending') {
      setNotice({ text: '该计划已经保存，可在项目计划中查看。' });
      return;
    }
    setEditingPlan(current);
  }
  async function saveTask(task: Task) {
    const { id, project_id, project_title, ...body } = task;
    const change = await api<Change>(id ? '/tasks/' + id : '/tasks', id ? 'PATCH' : 'POST', body, crypto.randomUUID());
    showChange(id ? '任务已更新' : '新任务已添加', change);
    await refresh();
  }
  async function toggleTask(task: Task) {
    try {
      const change = await api<Change>('/tasks/' + task.id, 'PATCH', { status: task.status === 'done' ? 'todo' : 'done' }, crypto.randomUUID());
      showChange(task.status === 'done' ? '任务已重新打开' : '任务已完成', change);
      await refresh();
    } catch (error) { showError(error); }
  }
  async function deleteTask() {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      const change = await api<Change>('/tasks/' + deleting.id, 'DELETE', undefined, crypto.randomUUID());
      setDeleting(null);
      showChange('任务已删除', change);
      await refresh();
    } catch (error) { showError(error); }
    finally { setDeleteBusy(false); }
  }
  async function savePlan(plan: Plan) {
    const change = await api<Change>('/plans/' + plan.id + '/commit', 'POST', plan, crypto.randomUUID());
    showChange('学习计划已保存，共 ' + plan.tasks.length + ' 个步骤', change);
    await refresh();
  }
  async function undo(action: string) {
    try {
      await api('/actions/' + action + '/undo', 'POST');
      setNotice({ text: '已撤销操作' });
      await refresh();
    } catch (error) { showError(error); }
  }
  async function seed() {
    setSeedBusy(true);
    try {
      const change = await api<Change>('/demo/seed', 'POST', undefined, crypto.randomUUID());
      showChange('已导入课程演示示例', change);
      await refresh();
    } catch (error) { showError(error); }
    finally { setSeedBusy(false); }
  }

  const renderTask = (task: Task) => <TaskRow key={task.id} task={task} onEdit={setEditing} onToggle={toggleTask} onDelete={setDeleting} />;
  const newTask = () => setEditing(freshTask());
  const dayTasks = tasks.filter(t => onDay(t, selectedDay)).sort((a,b) => Number(a.status === 'done') - Number(b.status === 'done') || byDate(a,b));
  const urgent = tasks.filter(t => t.status !== 'done' && (t.priority === 'high' || (t.due_date && t.due_date < currentDay))).sort(byDate).slice(0,3);
  const filtered = tasks.filter(t => {
    const matchesStatus = filter === 'all' || t.status === filter || (filter === 'overdue' && t.status !== 'done' && t.due_date && t.due_date < currentDay);
    const matchesSearch = [t.title,t.course,t.description].some(value => value.toLowerCase().includes(search.toLowerCase().trim()));
    return matchesStatus && matchesSearch && (!course || t.course === course);
  });
  const empty = (title: string, description: string, allowSeed = false) => <div className="empty-state">
    <div className="empty-icon"><BookOpen size={23} /></div><h3>{title}</h3><p>{description}</p>
    <div className="empty-actions">
      <button className="button primary" onClick={newTask}><Plus size={15} />新建任务</button>
      {allowSeed && !tasks.length && <button className="button secondary" onClick={seed} disabled={seedBusy}>
        {seedBusy ? <LoaderCircle size={15} className="spin"/> : <Sparkles size={15}/>}导入演示示例
      </button>}
    </div>
  </div>;
  function changeWeek(offset: number) {
    const next = addDays(week, offset);
    setWeek(next);
    setSelectedDay(next);
  }
  const weekControl = <div className="week-controls">
    <button className="icon-button" aria-label="上一周" onClick={() => changeWeek(-7)}><ChevronLeft size={17}/></button>
    <span>{shortDate(week)} – {shortDate(addDays(week, 6))}</span>
    <button className="icon-button" aria-label="下一周" onClick={() => changeWeek(7)}><ChevronRight size={17}/></button>
  </div>;

  return <div className="app-shell">
    <aside className="sidebar">
      <button className="brand" onClick={() => navigate('overview')}><span className="brand-icon"><GraduationCap size={25}/></span><span>课伴<small>CampusFlow</small></span></button>
      <div className="workspace-label">学习空间 <span>个人版</span></div>
      <nav aria-label="主导航">{pages.map(([id, label, Icon]) => <button key={id} className={'nav-item ' + (page === id ? 'active' : '')} aria-current={page === id ? 'page' : undefined} title={label} onClick={() => navigate(id)}>
        <Icon size={18}/><span>{label}</span>{id === 'tasks' && stats.pending > 0 && <b>{stats.pending}</b>}
      </button>)}</nav>
      <div className="sidebar-note"><Sparkles size={20}/><strong>大目标，从小步开始</strong><button onClick={startPlan}>和 AI 一起规划 <ArrowRight size={14}/></button></div>
      <div className="local-status"><i/>本地工作区<small>北京时间 · 数据保存在本机</small></div>
    </aside>

    <div className="workspace">
      <header className="topbar"><div className="breadcrumb">我的工作区 <ChevronRight size={14}/><strong>{pages.find(([id]) => id === page)?.[1]}</strong></div><div className="top-actions"><span className="today-label"><CalendarDays size={15}/>{dateTitle(currentDay)}</span><button className="icon-button mobile-ai" aria-label="打开 AI 助手" onClick={() => setAssistantOpen(!assistantOpen)}><MessageSquare size={20}/></button><div className="avatar">同</div></div></header>
      <div className="workspace-body">
        <main className="main-content">
          {serverError && <div className="error-banner" role="alert">{serverError} <button onClick={refresh}>重新连接</button></div>}
          {loading ? <div className="loading"><LoaderCircle className="spin" size={22}/>正在打开工作区…</div> : <>
          {page === 'overview' && <>
            <div className="page-heading"><div><span className="eyebrow">CAMPUSFLOW / TODAY</span><h1>今日概览</h1><p>理清今天的安排，把精力留给重要的事。</p></div><button className="button primary" onClick={newTask}><Plus size={17}/>新建任务</button></div>
            <section className="welcome-card">
              <div className="welcome-copy"><span className="welcome-tag"><Sparkles size={14}/>你的 AI 学习搭子</span><h2>有目标，也要有好计划。</h2><p>拆解学习目标，安排时间，跟进每一步进度。</p><button onClick={startPlan}>帮我拆解一个目标 <ArrowRight size={16}/></button></div>
              <div className="welcome-art" aria-hidden="true"><div className="art-orbit"/><div className="art-paper"><ClipboardList size={86} strokeWidth={1.1}/></div><div className="art-spark"><Sparkles size={25}/></div><div className="art-chip"><Check size={15}/>计划已就绪</div></div>
            </section>
            <div className="stats-grid">
              {[
                ['今日待办', stats.today, '项', CalendarDays],
                ['待完成', stats.pending, '项', ListTodo],
                ['已完成', stats.completed, '项', CheckCheck],
                ['完成率', stats.completion_rate, '%', Flag],
              ].map(([label, value, unit, icon]) => { const Icon = icon as typeof Flag; return <div className="stat-card" key={String(label)}><div>{String(label)}<Icon size={17}/></div><strong>{String(value)}<small>{String(unit)}</small></strong>{label === '待完成' && stats.overdue > 0 && <p className="late">{stats.overdue} 项已逾期</p>}{label === '完成率' && <div className="mini-progress"><span style={{width: stats.completion_rate + '%'}}/></div>}</div>; })}
            </div>
            <section className="panel">
              <div className="section-heading"><h2>一周安排</h2>{weekControl}</div>
              <div className="week-strip">{days.map((day,index) => <button key={day} className={(day === selectedDay ? 'selected ' : '') + (day === currentDay ? 'is-today' : '')} aria-pressed={day === selectedDay} onClick={() => setSelectedDay(day)}><span>{weekdays[index]}</span><strong>{Number(day.slice(-2))}</strong><i className={tasks.some(t => onDay(t, day)) ? 'has-task' : ''}/></button>)}</div>
              <div className="day-heading"><h3>{selectedDay === currentDay ? '今天' : shortDate(selectedDay)}的任务 <span>{dayTasks.length}</span></h3><button className="text-button" onClick={() => navigate('tasks')}>查看全部 <ArrowRight size={14}/></button></div>
              {dayTasks.length ? dayTasks.map(renderTask) : empty(tasks.length ? '这一天暂时没有安排' : '从一个小目标开始', '创建任务，或导入一组课堂演示示例。', true)}
            </section>
            <section className="panel"><div className="section-heading"><h2><Zap size={17}/>优先关注</h2><span className="muted">高优先级与逾期任务</span></div>{urgent.length ? urgent.map(renderTask) : <p className="all-clear">暂时没有需要优先处理的任务。</p>}</section>
          </>}

          {page === 'tasks' && <>
            <div className="page-heading"><div><span className="eyebrow">CAMPUSFLOW / TASKS</span><h1>我的任务</h1><p>查看、整理并跟进每一项待办。</p></div><button className="button primary" onClick={newTask}><Plus size={17}/>新建任务</button></div>
            <div className="task-toolbar"><label className="search-box"><Search size={17}/><input aria-label="搜索任务" placeholder="搜索任务或课程…" value={search} onChange={e => setSearch(e.target.value)}/></label><select aria-label="课程" value={course} onChange={e => setCourse(e.target.value)}><option value="">全部课程</option>{[...new Set(tasks.map(t => t.course))].map(c => <option key={c}>{c}</option>)}</select></div>
            <div className="filter-tabs">{[['all','全部任务'],['todo','待开始'],['doing','进行中'],['done','已完成'],['overdue','已逾期']].map(([value,label]) => <button key={value} aria-pressed={filter === value} className={filter === value ? 'active' : ''} onClick={() => setFilter(value)}>{label}</button>)}<span>{filtered.length} 项</span></div>
            <section className="panel">{filtered.length ? filtered.sort(byDate).map(renderTask) : tasks.length ? <div className="empty-state"><Search size={24}/><h3>没有匹配的任务</h3><p>试试其他关键词或筛选条件。</p></div> : empty('还没有任务', '把第一件想完成的事记录下来。', true)}</section>
          </>}

          {page === 'calendar' && <>
            <div className="page-heading"><div><span className="eyebrow">CAMPUSFLOW / CALENDAR</span><h1>学习日历</h1><p>看看这一周有哪些学习时段和截止日期。</p></div><button className="button primary" onClick={newTask}><Plus size={17}/>安排任务</button></div>
            <section className="panel"><div className="section-heading"><h2>周日历</h2>{weekControl}</div><div className="calendar-scroll"><div className="calendar-grid">{days.map((day,index) => <div className={'calendar-day ' + (day === currentDay ? 'current' : '')} key={day}><div className="calendar-date"><span>{weekdays[index]}</span><strong>{Number(day.slice(-2))}</strong></div><div className="calendar-events">{tasks.filter(t => onDay(t,day)).sort((a,b)=>(a.scheduled_start || 'z').localeCompare(b.scheduled_start || 'z')).map(t => <button key={t.id} className={'calendar-event ' + t.status} onClick={() => setEditing(t)}><span>{t.scheduled_start?.slice(0,10) === day ? t.scheduled_start.slice(11,16) + ' · ' + t.duration_minutes + ' 分钟' : '截止日期'}</span><strong>{t.title}</strong><small>{t.course}</small></button>)}</div></div>)}</div></div><p className="calendar-caption">北京时间。学习时段与截止日期分别显示。</p></section>
            <section className="panel"><div className="section-heading"><h2>待安排时间</h2></div>{tasks.some(t => !t.scheduled_start && t.status !== 'done') ? tasks.filter(t => !t.scheduled_start && t.status !== 'done').map(renderTask) : <p className="all-clear">暂无待排期任务。</p>}</section>
          </>}

          {page === 'projects' && <ProjectList tasks={tasks} plans={plans} onPlan={openDraft} onTask={setEditing} onStart={startPlan}/>}
          {page === 'settings' && <Settings health={health} tasks={tasks} seedBusy={seedBusy} onRefresh={refresh} onSeed={seed}/>}
          </>}
        </main>
        <Assistant health={health} open={assistantOpen} onClose={() => setAssistantOpen(false)} onSettings={openSettings} onChanged={refresh} onUndo={undo} onPlan={openDraft} prompt={prompt}/>
      </div>
    </div>
    {editing && <TaskEditor task={editing} onClose={() => setEditing(null)} onSave={saveTask}/>}
    {editingPlan && <PlanEditor plan={editingPlan} onClose={() => setEditingPlan(null)} onSave={savePlan}/>}
    {deleting && <Modal title="删除这项任务？" onClose={() => !deleteBusy && setDeleting(null)}><div className="delete-content"><p>「{deleting.title}」将从任务列表和日历移除，可撤销。</p><div className="modal-footer"><button className="button secondary" disabled={deleteBusy} onClick={() => setDeleting(null)}>取消</button><button className="button danger" disabled={deleteBusy} onClick={deleteTask}><Trash2 size={15}/>删除任务</button></div></div></Modal>}
    {notice && <div className={'toast ' + (notice.error ? 'error' : '')} role="status">{notice.error ? <Flag size={17}/> : <Check size={17}/>}<span>{notice.text}</span>{notice.action && <button onClick={() => undo(notice.action!)}>撤销</button>}<button className="toast-close" aria-label="关闭提示" onClick={() => setNotice(null)}><X size={16}/></button></div>}
  </div>;
}
