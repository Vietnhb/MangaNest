import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Boxes,
  Check,
  ChevronRight,
  CircleStop,
  Download,
  Eye,
  FileJson,
  Gauge,
  Image as ImageIcon,
  LoaderCircle,
  Menu,
  PanelTop,
  PenLine,
  Play,
  Plus,
  RefreshCw,
  Settings2,
  Sparkles,
  Upload,
  Users,
  WandSparkles,
  X,
} from 'lucide-react'
import './App.css'
import './Dashboard.css'
import { Dashboard } from './Dashboard'
import { MangaCanvas } from './MangaCanvas'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const ACTIVE_JOB_KEY = 'mangaforge.activeJobId'

type RenderMode = 'prompt_only' | 'mock' | 'comfyui'
type JobState = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
type StudioPhase = 'story' | 'characters' | 'storyboard' | 'artwork' | 'review' | 'export'

interface Dialogue { speaker: string; text: string; delivery: string }
interface StoryPanel {
  panel_id: string; panel_number: number; setting: string; time_of_day: string
  characters: string[]; action: string; visual_description: string; shot_type: string
  camera_angle: string; mood: string; dialogue: Dialogue[]; narration?: string; sound_effects: string[]
}
interface StoryPage { page_number: number; purpose: string; panels: StoryPanel[]; page_turn_hook?: string }
interface Character { name: string; role: string; appearance: string; personality: string; motivation: string }
interface OutlineBeat { beat_number: number; name: string; summary: string; emotional_goal: string }
interface LayoutPanel {
  panel_id: string; reading_order: number; box: { x: number; y: number; width: number; height: number }
  shape: string; border: string; bleed: boolean; focal_weight: string; composition_notes: string
}
interface PromptPanel {
  panel_id: string; positive_prompt: string; negative_prompt: string; character_consistency: string[]
  composition_control: string; dialogue_overlay: string[]
  identity_mode?: 'auto' | 'reference' | 'off'; identity_strength?: number | null
  parameters: { width: number; height: number; steps: number; cfg_scale: number; sampler: string; aspect_ratio: string }
}
export interface MangaResult {
  run_id: string; status: string; model: string; revision_count: number
  series_id?: string; episode_id?: string; episode_number?: number
  story: {
    title: string; logline: string; genre: string[]; themes: string[]; visual_tone: string
    characters: Character[]; outline: OutlineBeat[]; pages: StoryPage[]
  }
  layout: { design_rationale: string; pages: { page_number: number; layout_strategy: string; panels: LayoutPanel[] }[] }
  generation: { recommended_checkpoint: string; global_style_prefix: string; panels: PromptPanel[]; continuity_notes: string[] }
  render: {
    backend: RenderMode; checkpoint: string
    panels: { panel_id: string; status: string; image_url?: string; seed?: number }[]
    identity_references?: Record<string, string>
    pages?: { page_number: number; image_url: string; width: number; height: number }[]
    publication?: { pdf_url: string; cbz_url: string; manifest_url: string }
  }
  critique: {
    overall_score: number; decision: string; summary: string
    panel_critiques: { panel_id: string; score: number; strengths: string[]; issues: string[]; correction?: string }[]
    regeneration_instructions: string[]
    lora_training: { eligible: boolean; reason: string; quality_score: number; caption_tags: string[] }
  }
}
export interface BubbleEdit {
  bubble_id: string; line_id?: string; speaker?: string; text: string; delivery: string
  bubble_type: 'speech' | 'thought' | 'whisper' | 'shout' | 'caption' | 'sfx'
  box: { x: number; y: number; width: number; height: number }
  tail_x?: number; tail_y?: number; reading_order: number; locked: boolean
}
export interface PanelEdit {
  panel_id: string; box: { x: number; y: number; width: number; height: number }; reading_order: number
  bubbles: BubbleEdit[]; artwork_locked: boolean; panel_locked: boolean; status: 'draft' | 'review' | 'approved' | 'locked'
}
export interface EpisodeEdit {
  id: string; revision: number; status: string
  generation?: MangaResult['generation']; render?: MangaResult['render']
  critique?: MangaResult['critique']
  editor: { pages: { page_number: number; panels: PanelEdit[] }[] }
}
interface MangaJob {
  job_id: string; state: JobState; stage: string; progress: number; message: string
  created_at: string; updated_at: string; result?: MangaResult; error?: string
}
interface SystemStatus {
  status: string; llm: { online: boolean; provider: string; model: string; free_only?: boolean; models?: string[] }; comfyui: { online: boolean }
  render_backend: string; checkpoint: { name: string; ready: boolean }
}
interface SeriesSummary {
  id: string; title: string; episode_count: number
  premise?: string; visual_style?: string; updated_at?: string
}

const productionStages = [
  { id: 'story', label: 'Kịch bản', icon: BookOpen },
  { id: 'layout', label: 'Phân cảnh', icon: PanelTop },
  { id: 'generation', label: 'Prompt', icon: WandSparkles },
  { id: 'render', label: 'Dựng hình', icon: ImageIcon },
  { id: 'critique', label: 'Kiểm duyệt', icon: Eye },
]

const studioPhases: { id: StudioPhase; label: string; hint: string; icon: typeof BookOpen }[] = [
  { id: 'story', label: 'Kịch bản', hint: 'Cốt truyện & nhịp kể', icon: BookOpen },
  { id: 'characters', label: 'Nhân vật', hint: 'Hồ sơ nhất quán', icon: Users },
  { id: 'storyboard', label: 'Phân cảnh', hint: 'Panel & bố cục', icon: PanelTop },
  { id: 'artwork', label: 'Hình ảnh', hint: 'Render & prompt', icon: ImageIcon },
  { id: 'review', label: 'Duyệt', hint: 'Chất lượng & sửa lỗi', icon: Eye },
  { id: 'export', label: 'Xuất bản', hint: 'Dữ liệu sản xuất', icon: Download },
]

const presets = [
  { id: 'quick', name: 'Bản nháp nhanh', caption: '1 trang · ảnh mô phỏng', pages: 1, mode: 'mock' as RenderMode, icon: Gauge },
  { id: 'script', name: 'Kịch bản trước', caption: '2 trang · chưa dựng ảnh', pages: 2, mode: 'prompt_only' as RenderMode, icon: PenLine },
  { id: 'quality', name: 'Ảnh manga thật', caption: '1 trang · Animagine XL', pages: 1, mode: 'comfyui' as RenderMode, icon: Sparkles },
]

function App() {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [series, setSeries] = useState<SeriesSummary[]>([])
  const [screen, setScreen] = useState<'home' | 'create' | 'running' | 'studio'>('home')
  const [createStep, setCreateStep] = useState(1)
  const [phase, setPhase] = useState<StudioPhase>('story')
  const [job, setJob] = useState<MangaJob | null>(null)
  const [result, setResult] = useState<MangaResult | null>(null)
  const [isDemo, setIsDemo] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [mobileNav, setMobileNav] = useState(false)
  const [selectedPage, setSelectedPage] = useState(1)
  const [selectedPanel, setSelectedPanel] = useState<string | null>(null)
  const [form, setForm] = useState({
    idea: '',
    target_pages: 1,
    genre: 'fantasy, mystery',
    audience: 'teen',
    manga_style: 'cinematic black-and-white Japanese manga',
    render_mode: 'comfyui' as RenderMode,
    max_revisions: 0,
    series_id: '',
    episode_number: 1,
  })
  const activeJobId = job?.job_id

  const refreshStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/system-status`)
      if (response.ok) setStatus(await response.json())
    } catch { setStatus(null) }
  }
  const refreshSeries = async () => {
    try { const response = await fetch(`${API_BASE}/story-series`); if (response.ok) setSeries(await response.json()) } catch { /* backend status already reports connectivity */ }
  }

  useEffect(() => { void refreshStatus(); void refreshSeries() }, [])

  useEffect(() => {
    const jobId = window.localStorage.getItem(ACTIVE_JOB_KEY)
    if (!jobId) return
    void fetch(`${API_BASE}/manga-jobs/${jobId}`).then(async (response) => {
      if (!response.ok) throw new Error('Job is no longer available')
      const recovered: MangaJob = await response.json()
      setJob(recovered)
      if (recovered.state === 'completed' && recovered.result) {
        setResult(recovered.result)
        setSelectedPanel(recovered.result.story.pages[0]?.panels[0]?.panel_id ?? null)
        setScreen('studio')
        setPhase('storyboard')
        window.localStorage.removeItem(ACTIVE_JOB_KEY)
      } else if (recovered.state === 'queued' || recovered.state === 'running') {
        setScreen('running')
      } else {
        window.localStorage.removeItem(ACTIVE_JOB_KEY)
      }
    }).catch(() => window.localStorage.removeItem(ACTIVE_JOB_KEY))
  }, [])

  useEffect(() => {
    if (screen !== 'running' || !activeJobId) return
    const startedAt = Date.now()
    const clock = window.setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000)
    const poll = window.setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/manga-jobs/${activeJobId}`)
        if (!response.ok) throw new Error('Không đọc được trạng thái tác vụ')
        const next: MangaJob = await response.json()
        setJob(next)
        if (next.state === 'completed' && next.result) {
          window.localStorage.removeItem(ACTIVE_JOB_KEY)
          setResult(next.result)
          setSelectedPanel(next.result.story.pages[0]?.panels[0]?.panel_id ?? null)
          setScreen('studio')
          setPhase('storyboard')
          void refreshSeries()
        } else if (next.state === 'failed') {
          window.localStorage.removeItem(ACTIVE_JOB_KEY)
          setError(next.error || 'Pipeline gặp lỗi')
        } else if (next.state === 'cancelled') {
          window.localStorage.removeItem(ACTIVE_JOB_KEY)
          setScreen('create')
        }
      } catch (pollError) {
        setError(pollError instanceof Error ? pollError.message : 'Mất kết nối backend')
      }
    }, 1500)
    return () => { window.clearInterval(clock); window.clearInterval(poll) }
  }, [screen, activeJobId])

  const startJob = async (event?: FormEvent) => {
    event?.preventDefault()
    setError(null)
    try {
      const response = await fetch(`${API_BASE}/manga-jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          series_id: form.series_id || null,
          episode_number: form.series_id ? form.episode_number : null,
          genre: form.genre.split(',').map((value) => value.trim()).filter(Boolean),
        }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Không thể khởi tạo dự án')
      setResult(null)
      setIsDemo(false)
      setElapsed(0)
      setJob(payload)
      window.localStorage.setItem(ACTIVE_JOB_KEY, payload.job_id)
      setScreen('running')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Có lỗi không xác định')
    }
  }

  const cancelJob = async () => {
    if (!job) return
    await fetch(`${API_BASE}/manga-jobs/${job.job_id}/cancel`, { method: 'POST' })
    window.localStorage.removeItem(ACTIVE_JOB_KEY)
    setScreen('create')
    setJob(null)
  }

  const loadDemo = async () => {
    setError(null)
    try {
      const response = await fetch(`${API_BASE}/demo-project`)
      if (!response.ok) throw new Error('Không tìm thấy dự án mẫu')
      const demo: MangaResult = await response.json()
      setResult(demo)
      setIsDemo(true)
      setSelectedPanel(demo.story.pages[0]?.panels[0]?.panel_id ?? null)
      setScreen('studio')
      setPhase('storyboard')
    } catch (demoError) {
      setError(demoError instanceof Error ? demoError.message : 'Không mở được dự án mẫu')
    }
  }

  const openSeries = async (seriesId: string) => {
    setError(null)
    try {
      const response = await fetch(`${API_BASE}/story-series/${seriesId}/latest-result`)
      if (!response.ok) throw new Error('Series has no completed production')
      const production: MangaResult = await response.json()
      setResult(production)
      setIsDemo(false)
      setSelectedPage(production.story.pages[0]?.page_number || 1)
      setSelectedPanel(production.story.pages[0]?.panels[0]?.panel_id ?? null)
      setScreen('studio')
      setPhase('storyboard')
    } catch {
      const selected = series.find((item) => item.id === seriesId)
      setForm((current) => ({ ...current, series_id: seriesId, episode_number: (selected?.episode_count || 0) + 1 }))
      setCreateStep(1)
      setScreen('create')
    }
  }

  const newProject = () => {
    setScreen('create'); setCreateStep(1); setResult(null); setJob(null); setIsDemo(false); setError(null)
  }

  return (
    <div className="app-shell">
      {!(screen === 'studio' && phase === 'storyboard') && <Header screen={screen} status={status} onHome={() => screen !== 'running' && setScreen('home')} onRefresh={refreshStatus} onNew={newProject} onMenu={() => setMobileNav(!mobileNav)} />}
      {screen === 'home' && <Dashboard status={status} series={series} onCreate={newProject} onDemo={loadDemo} onOpen={(seriesId) => void openSeries(seriesId)} onRefresh={refreshStatus} />}
      {screen === 'create' && (
        <CreateStudio
          step={createStep}
          form={form}
          error={error}
          status={status}
          series={series}
          onChange={setForm}
          onStep={setCreateStep}
          onStart={startJob}
          onDemo={loadDemo}
        />
      )}
      {screen === 'running' && job && (
        <ProductionRoom job={job} elapsed={elapsed} error={error} onCancel={cancelJob} />
      )}
      {screen === 'studio' && result && (
        <StudioWorkspace
          result={result}
          phase={phase}
          isDemo={isDemo}
          mobileNav={mobileNav}
          selectedPage={selectedPage}
          selectedPanel={selectedPanel}
          onPhase={(next) => { setPhase(next); setMobileNav(false) }}
          onPage={setSelectedPage}
          onPanel={setSelectedPanel}
          onNew={newProject}
        />
      )}
    </div>
  )
}

function Header({ screen, status, onHome, onRefresh, onNew, onMenu }: {
  screen: 'home' | 'create' | 'running' | 'studio'; status: SystemStatus | null
  onHome: () => void; onRefresh: () => void; onNew: () => void; onMenu: () => void
}) {
  return <header className="topbar">
    <button className="mobile-menu" onClick={onMenu} aria-label="Mở menu"><Menu size={20} /></button>
    <button className="brand" onClick={onHome}>
      <span className="brand-mark">漫</span>
      <span><small>AI CREATION SUITE</small><strong>MangaForge <em>Studio</em></strong></span>
    </button>
    <nav className="global-nav"><button className={screen === 'home' ? 'active' : ''} onClick={onHome}>Khám phá</button><button className={screen === 'studio' ? 'active' : ''} onClick={onHome}>Dự án</button><button onClick={onNew}>Sáng tác</button></nav>
    <div className="runtime-pills">
      <span className={status ? 'online' : 'offline'}><i />API</span>
      <span className={status?.llm.online ? 'online' : 'offline'}><i />{status?.llm.provider === 'openrouter' ? 'OPENROUTER FREE' : 'LOCAL AI'}</span>
      <span className={status?.comfyui.online ? 'online' : 'offline'}><i />COMFYUI</span>
      <button onClick={onRefresh} aria-label="Làm mới trạng thái"><RefreshCw size={15} /></button>
      <button className="new-project-top" onClick={onNew} disabled={screen === 'running'}><Plus size={15} /> Tạo manga</button>
    </div>
  </header>
}

function CreateStudio({ step, form, error, status, series, onChange, onStep, onStart, onDemo }: {
  step: number; form: typeof initialForm; error: string | null; status: SystemStatus | null; series: SeriesSummary[]
  onChange: (value: typeof initialForm) => void; onStep: (value: number) => void
  onStart: (event?: FormEvent) => void; onDemo: () => void
}) {
  const canContinue = form.idea.trim().length >= 10
  return <main className="create-shell">
    <aside className="create-aside">
      <span className="section-number">01</span>
      <p className="eyebrow">NEW PRODUCTION</p>
      <h1>Biến ý tưởng thành manga.</h1>
      <p>Mỗi bước đều có thể xem lại. Hình ảnh chỉ được dựng sau khi kịch bản và phân cảnh đã sẵn sàng.</p>
      <div className="create-steps">
        {['Ý tưởng', 'Phong cách', 'Xác nhận'].map((label, index) => (
          <button key={label} className={step === index + 1 ? 'active' : step > index + 1 ? 'done' : ''} onClick={() => step > index + 1 && onStep(index + 1)}>
            <span>{step > index + 1 ? <Check size={14} /> : index + 1}</span><strong>{label}</strong>
          </button>
        ))}
      </div>
      <button className="demo-link" onClick={onDemo}><Play size={14} /> Xem dự án mẫu trước</button>
    </aside>

    <section className="create-main">
      {step === 1 && <div className="form-stage">
        <p className="eyebrow">BƯỚC 1 / 3 · STORY BRIEF</p>
        <h2>Bạn muốn kể câu chuyện gì?</h2>
        <p className="stage-lead">Viết như đang kể cho một người bạn. AI sẽ lo cấu trúc, nhịp truyện và chia panel.</p>
        <label className="series-picker"><span>Bộ truyện</span><select value={form.series_id} onChange={(event) => { const selected = series.find((item) => item.id === event.target.value); onChange({ ...form, series_id: event.target.value, episode_number: selected ? selected.episode_count + 1 : 1 }) }}><option value="">Tạo bộ truyện mới</option>{series.map((item) => <option key={item.id} value={item.id}>Tiếp tục “{item.title}” · Tập {item.episode_count + 1}</option>)}</select><small>{form.series_id ? 'AI sẽ nạp Story Bible, trạng thái cuối tập và các trang trước.' : 'Kết quả sẽ tự trở thành tập 1 của một bộ truyện mới.'}</small></label>
        <label className="big-idea">
          <span>Ý tưởng cốt truyện</span>
          <textarea autoFocus value={form.idea} maxLength={5000} onChange={(event) => onChange({ ...form, idea: event.target.value })} placeholder="Ví dụ: Một nữ sinh phát hiện cây bút có thể thay đổi ngày mai, nhưng mỗi nét vẽ xóa đi một ký ức của cô..." />
          <small>{form.idea.length} / 5000</small>
        </label>
        <div className="inspiration-row">
          <span>Gợi ý nhanh</span>
          {['Bí ẩn học đường', 'Phiêu lưu kỳ ảo', 'Tình bạn & trưởng thành'].map((idea) => <button key={idea} onClick={() => onChange({ ...form, idea: `${idea}: ` })}>{idea}</button>)}
        </div>
        <div className="form-actions"><span /><button className="primary" disabled={!canContinue} onClick={() => onStep(2)}>Tiếp tục <ArrowRight size={17} /></button></div>
      </div>}

      {step === 2 && <div className="form-stage">
        <p className="eyebrow">BƯỚC 2 / 3 · PRODUCTION MODE</p>
        <h2>Chọn cách sản xuất</h2>
        <p className="stage-lead">Với RTX 3050 4GB, nên bắt đầu bằng bản nháp 1 trang rồi mới dựng ảnh thật.</p>
        <div className="preset-grid">
          {presets.map(({ id, name, caption, pages, mode, icon: Icon }) => {
            const active = form.target_pages === pages && form.render_mode === mode
            return <button key={id} className={active ? 'preset active' : 'preset'} onClick={() => onChange({ ...form, target_pages: pages, render_mode: mode })}>
              <span className="preset-icon"><Icon size={22} /></span><strong>{name}</strong><small>{caption}</small>{active && <i><Check size={13} /></i>}
            </button>
          })}
        </div>
        <div className="field-grid">
          <label><span>Độc giả</span><select value={form.audience} onChange={(e) => onChange({ ...form, audience: e.target.value })}><option value="children">Thiếu nhi</option><option value="teen">Thanh thiếu niên</option><option value="adult">Người trưởng thành</option></select></label>
          <label><span>Thể loại</span><input value={form.genre} onChange={(e) => onChange({ ...form, genre: e.target.value })} /></label>
          <label className="wide"><span>Phong cách hình ảnh</span><select value={form.manga_style} onChange={(e) => onChange({ ...form, manga_style: e.target.value })}><option value="cinematic black-and-white Japanese manga">Manga điện ảnh đen trắng</option><option value="clean shonen manga, dynamic ink lines">Shōnen năng động</option><option value="delicate shojo manga, elegant screentones">Shōjo tinh tế</option><option value="dark seinen manga, dramatic shadows">Seinen trưởng thành</option></select></label>
        </div>
        <details className="advanced"><summary><Settings2 size={16} /> Thiết lập nâng cao</summary><div><label>Số trang <input type="number" min="1" max="4" value={form.target_pages} onChange={(e) => onChange({ ...form, target_pages: Number(e.target.value) })} /></label><label>Số lần AI tự sửa <input type="number" min="0" max="1" value={form.max_revisions} onChange={(e) => onChange({ ...form, max_revisions: Number(e.target.value) })} /></label></div></details>
        <div className="form-actions"><button className="secondary" onClick={() => onStep(1)}><ArrowLeft size={16} /> Quay lại</button><button className="primary" onClick={() => onStep(3)}>Kiểm tra <ArrowRight size={17} /></button></div>
      </div>}

      {step === 3 && <div className="form-stage review-stage">
        <p className="eyebrow">BƯỚC 3 / 3 · READY TO FORGE</p>
        <h2>Kiểm tra trước khi chạy</h2>
        <div className="brief-preview"><span>Ý tưởng</span><p>{form.idea}</p></div>
        <div className="review-facts">
          <div><BookOpen /><span><small>Quy mô</small><strong>{form.target_pages} trang</strong></span></div>
          <div><ImageIcon /><span><small>Đầu ra</small><strong>{form.render_mode === 'comfyui' ? 'Ảnh manga thật' : form.render_mode === 'mock' ? 'Ảnh mô phỏng' : 'Chỉ tạo prompt'}</strong></span></div>
          <div><RefreshCw /><span><small>Tự sửa</small><strong>{form.max_revisions} lần</strong></span></div>
        </div>
        {form.target_pages > 2 && <div className="warning"><Gauge size={18} /><span><strong>Tác vụ nặng trên máy này</strong>Hãy chia chương thành từng đợt 1–2 trang để tránh chờ quá lâu.</span></div>}
        {!status?.llm.online && <div className="warning danger"><X size={18} /><span><strong>AI provider chưa sẵn sàng</strong>Kiểm tra API key, kết nối hoặc giới hạn của model miễn phí.</span></div>}
        {error && <div className="warning danger"><X size={18} /><span><strong>Không thể bắt đầu</strong>{error}</span></div>}
        <div className="form-actions"><button className="secondary" onClick={() => onStep(2)}><ArrowLeft size={16} /> Quay lại</button><button className="primary forge" disabled={!status?.llm.online} onClick={() => void onStart()}><Sparkles size={17} /> Bắt đầu sản xuất</button></div>
      </div>}
    </section>
  </main>
}

const initialForm = { idea: '', target_pages: 1, genre: '', audience: '', manga_style: '', render_mode: 'comfyui' as RenderMode, max_revisions: 0, series_id: '', episode_number: 1 }

function ProductionRoom({ job, elapsed, error, onCancel }: { job: MangaJob; elapsed: number; error: string | null; onCancel: () => void }) {
  const currentIndex = productionStages.findIndex((stage) => stage.id === job.stage)
  return <main className="production-room">
    <div className="production-card">
      <div className="production-orbit"><Sparkles size={30} /><span /></div>
      <p className="eyebrow">LIVE PRODUCTION · {job.job_id.slice(0, 8).toUpperCase()}</p>
      <h1>{job.state === 'failed' ? 'Tác vụ đã dừng' : 'Đang tạo manga của bạn'}</h1>
      <p className="real-progress-note">Đây là tiến độ thật từ LangGraph, không phải đồng hồ ước tính.</p>
      <div className="stage-track">
        {productionStages.map(({ id, label, icon: Icon }, index) => {
          const complete = currentIndex > index || job.state === 'completed'
          const active = job.stage === id
          return <div key={id} className={complete ? 'complete' : active ? 'active' : ''}><span>{complete ? <Check size={16} /> : active ? <LoaderCircle size={16} className="spin" /> : <Icon size={16} />}</span><strong>{label}</strong></div>
        })}
      </div>
      <div className="progress-copy"><strong>{job.message}</strong><span>{job.progress}%</span></div>
      <div className="progress-bar"><i style={{ width: `${job.progress}%` }} /></div>
      <div className="production-meta"><span>Thời gian <strong>{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')}</strong></span><span>Trạng thái <strong>{job.state}</strong></span></div>
      {(error || job.error) && <div className="job-error">{error || job.error}</div>}
      <div className="production-tip"><Sparkles size={16} /><span><strong>{job.state === 'failed' ? 'Không mất dữ liệu demo.' : 'Bạn có thể hủy an toàn.'}</strong> {job.state === 'failed' ? 'Quay lại để giảm số trang hoặc đổi sang bản nháp rồi chạy lại.' : 'Kết quả chỉ xuất hiện khi toàn bộ pipeline hoàn tất; dự án mẫu sẽ không bị trộn vào tác vụ này.'}</span></div>
      <button className="cancel-button" onClick={onCancel}>{job.state === 'failed' ? <ArrowLeft size={17} /> : <CircleStop size={17} />} {job.state === 'failed' ? 'Quay lại thiết lập' : 'Hủy tác vụ'}</button>
    </div>
  </main>
}

function StudioWorkspace({ result, phase, isDemo, mobileNav, selectedPage, selectedPanel, onPhase, onPage, onPanel, onNew }: {
  result: MangaResult; phase: StudioPhase; isDemo: boolean; mobileNav: boolean; selectedPage: number; selectedPanel: string | null
  onPhase: (phase: StudioPhase) => void; onPage: (page: number) => void; onPanel: (panel: string) => void; onNew: () => void
}) {
  const [episode, setEpisode] = useState<EpisodeEdit>(() => buildLocalEditor(result))

  useEffect(() => {
    setEpisode(buildLocalEditor(result))
    if (!result.episode_id) return
    void fetch(`${API_BASE}/story-episodes/${result.episode_id}`).then(async (response) => {
      if (!response.ok) throw new Error('Không tải được dữ liệu biên tập')
      setEpisode(await response.json())
    }).catch(() => { /* Keep the local editor available when persistence is offline. */ })
  }, [result])

  if (phase === 'storyboard') {
    return <MangaCanvas
      result={result}
      episode={episode}
      page={selectedPage}
      onPage={onPage}
      onEpisode={setEpisode}
      onExit={() => onPhase('story')}
      onArtwork={() => onPhase('artwork')}
    />
  }

  return <div className="studio-layout">
    <aside className={`studio-nav ${mobileNav ? 'open' : ''}`}>
      <div className="project-heading"><span>{isDemo ? 'DỰ ÁN MẪU' : 'DỰ ÁN HIỆN TẠI'}</span><h2>{result.story.title}</h2><small>{result.story.pages.length} trang · {result.render.panels.length} panel</small></div>
      <nav>{studioPhases.map(({ id, label, hint, icon: Icon }, index) => <button key={id} className={phase === id ? 'active' : ''} onClick={() => onPhase(id)}><span className="nav-index">0{index + 1}</span><Icon size={18} /><span><strong>{label}</strong><small>{hint}</small></span><ChevronRight size={15} /></button>)}</nav>
      <button className="aside-new" onClick={onNew}><Plus size={16} /> Tạo dự án khác</button>
    </aside>
    <main className="workspace">
      <div className="workspace-head"><div><p className="eyebrow">{studioPhases.find((item) => item.id === phase)?.hint}</p><h1>{studioPhases.find((item) => item.id === phase)?.label}</h1></div><div className="workspace-score"><span>Điểm kiểm duyệt</span><strong>{result.critique.overall_score.toFixed(1)}</strong><small>/10</small></div></div>
      {phase === 'story' && <StoryDesk result={result} />}
      {phase === 'characters' && <CharacterDeskV2 result={result} episode={episode} onEpisode={setEpisode} />}
      {phase === 'artwork' && <ArtworkDesk result={result} episode={episode} onEpisode={setEpisode} selected={selectedPanel} onSelect={onPanel} />}
      {phase === 'review' && <ReviewDesk result={result} />}
      {phase === 'export' && <ExportDesk result={result} episode={episode} />}
    </main>
  </div>
}

function StoryDesk({ result }: { result: MangaResult }) {
  return <div className="desk story-desk"><section className="story-hero"><div className="tag-row">{result.story.genre.map((genre) => <span key={genre}>{genre}</span>)}</div><h2>{result.story.logline}</h2><p>{result.story.visual_tone}</p></section><div className="desk-title"><div><p className="eyebrow">STORY BEATS</p><h3>Nhịp truyện</h3></div><span>{result.story.outline.length} nhịp</span></div><div className="beat-list">{result.story.outline.map((beat) => <article key={beat.beat_number}><span>{String(beat.beat_number).padStart(2, '0')}</span><div><h4>{beat.name}</h4><p>{beat.summary}</p><small>{beat.emotional_goal}</small></div></article>)}</div></div>
}

const referenceViews = [
  ['front', 'Chính diện'], ['three_quarter', 'Góc 3/4'], ['profile', 'Nghiêng'],
  ['back', 'Sau lưng'], ['full_body', 'Toàn thân'], ['expression', 'Biểu cảm'],
] as const

function outputImageUrl(path: string) {
  const normalized = path.replaceAll('\\', '/')
  const marker = '/outputs/'
  const index = normalized.toLowerCase().lastIndexOf(marker)
  return index >= 0 ? `${API_BASE}${normalized.slice(index)}` : ''
}

async function identityHash(value: string) {
  const bytes = new TextEncoder().encode(value.trim().toLocaleLowerCase())
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, '0')).join('').slice(0, 16)
}

function CharacterDeskV2({ result, episode, onEpisode }: { result: MangaResult; episode: EpisodeEdit; onEpisode: (episode: EpisodeEdit) => void }) {
  const [keys, setKeys] = useState<Record<string, string>>({})
  const [uploading, setUploading] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const references = episode.render?.identity_references || result.render.identity_references || {}

  useEffect(() => {
    void Promise.all(result.story.characters.map(async (character) => {
      const anchor = result.generation.panels.flatMap((panel) => panel.character_consistency)
        .find((item) => item.toLocaleLowerCase().includes(character.name.toLocaleLowerCase()))
      return [character.name, anchor ? await identityHash(anchor) : ''] as const
    })).then((entries) => setKeys(Object.fromEntries(entries)))
  }, [result])

  const upload = async (character: Character, view: string, file?: File) => {
    if (!file || !result.episode_id) return
    const token = `${character.name}:${view}`
    setUploading(token); setMessage(null)
    const body = new FormData()
    body.set('expected_revision', String(episode.revision)); body.set('view', view); body.set('image', file)
    try {
      const response = await fetch(`${API_BASE}/story-episodes/${result.episode_id}/character-references/${encodeURIComponent(character.name)}`, { method: 'POST', body })
      if (!response.ok) throw new Error((await response.json()).detail || 'Không thể nhập ảnh tham chiếu')
      onEpisode(await response.json())
      setMessage(`Đã khóa góc ${view} cho ${character.name}.`)
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : 'Không thể nhập ảnh tham chiếu')
    } finally { setUploading(null) }
  }

  return <div className="desk character-bible-desk"><div className="desk-title"><div><p className="eyebrow">VISUAL CHARACTER BIBLE</p><h3>Hồ sơ đa góc nhân vật</h3></div><span>{result.story.characters.length} nhân vật</span></div><p className="desk-intro">Duyệt hoặc nhập bộ ảnh chính diện, 3/4, nghiêng, sau lưng, toàn thân và biểu cảm trước khi render panel. Hệ thống tự chọn góc gần nhất theo camera; ảnh tham chiếu không còn bị áp tùy tiện lên cảnh rộng.</p>{message && <div className="reference-message">{message}</div>}<div className="character-bible-list">{result.story.characters.map((character, index) => <article className="character-bible-card" key={character.name}><header><div className="character-avatar"><Users size={28} /><span>0{index + 1}</span></div><div><small>{character.role}</small><h3>{character.name}</h3><p>{character.appearance}</p></div></header><div className="reference-view-grid">{referenceViews.map(([view, label]) => { const path = references[`${keys[character.name]}:${view}`]; const url = path ? outputImageUrl(path) : ''; const token = `${character.name}:${view}`; return <label className={url ? 'has-reference' : ''} key={view}>{url ? <img src={url} alt={`${character.name} ${label}`} /> : <span><Upload size={18} />{uploading === token ? 'Đang tải…' : label}</span>}<input type="file" accept="image/png,image/jpeg,image/webp" disabled={uploading !== null || !result.episode_id} onChange={(event) => void upload(character, view, event.target.files?.[0])} /><i>{label}</i></label> })}</div></article>)}</div></div>
}

function layoutNeedsRepair(panels: LayoutPanel[]) {
  const overlaps = (a: LayoutPanel, b: LayoutPanel) => {
    if (a.shape === 'inset' || b.shape === 'inset') return false
    const horizontal = Math.min(a.box.x + a.box.width, b.box.x + b.box.width) - Math.max(a.box.x, b.box.x)
    const vertical = Math.min(a.box.y + a.box.height, b.box.y + b.box.height) - Math.max(a.box.y, b.box.y)
    return horizontal > 0.005 && vertical > 0.005
  }
  return panels.some((panel) => panel.box.x + panel.box.width > 1.005 || panel.box.y + panel.box.height > 1.005)
    || panels.some((panel, index) => panels.slice(index + 1).some((other) => overlaps(panel, other)))
}

function fallbackBoxes(count: number) {
  const templates: Record<number, { x: number; y: number; width: number; height: number }[]> = {
    1: [{ x: .035, y: .025, width: .93, height: .95 }],
    2: [{ x: .035, y: .025, width: .93, height: .455 }, { x: .035, y: .51, width: .93, height: .465 }],
    3: [{ x: .035, y: .025, width: .93, height: .44 }, { x: .51, y: .495, width: .455, height: .48 }, { x: .035, y: .495, width: .445, height: .48 }],
    4: [{ x: .51, y: .025, width: .455, height: .455 }, { x: .035, y: .025, width: .445, height: .455 }, { x: .51, y: .51, width: .455, height: .465 }, { x: .035, y: .51, width: .445, height: .465 }],
    5: [{ x: .035, y: .025, width: .93, height: .30 }, { x: .51, y: .355, width: .455, height: .29 }, { x: .035, y: .355, width: .445, height: .29 }, { x: .51, y: .675, width: .455, height: .30 }, { x: .035, y: .675, width: .445, height: .30 }],
    6: [{ x: .51, y: .025, width: .455, height: .29 }, { x: .035, y: .025, width: .445, height: .29 }, { x: .51, y: .345, width: .455, height: .30 }, { x: .035, y: .345, width: .445, height: .30 }, { x: .51, y: .675, width: .455, height: .30 }, { x: .035, y: .675, width: .445, height: .30 }],
    7: [{ x: .51, y: .025, width: .455, height: .28 }, { x: .035, y: .025, width: .445, height: .28 }, { x: .51, y: .335, width: .455, height: .28 }, { x: .035, y: .335, width: .445, height: .28 }, { x: .68, y: .645, width: .285, height: .33 }, { x: .3575, y: .645, width: .2925, height: .33 }, { x: .035, y: .645, width: .2925, height: .33 }],
  }
  if (templates[count]) return templates[count]
  const columns = 3
  const rows = Math.ceil(count / columns)
  const gap = .025
  const width = (0.93 - gap * (columns - 1)) / columns
  const height = (0.95 - gap * (rows - 1)) / rows
  return Array.from({ length: count }, (_, index) => {
    const row = Math.floor(index / columns)
    const rtlColumn = columns - 1 - (index % columns)
    return { x: .035 + rtlColumn * (width + gap), y: .025 + row * (height + gap), width, height }
  })
}

function safePageLayout(panels: LayoutPanel[]) {
  const sorted = [...panels].sort((a, b) => a.reading_order - b.reading_order)
  if (!layoutNeedsRepair(sorted)) return { panels: sorted, repaired: false }
  const boxes = fallbackBoxes(sorted.length)
  return { panels: sorted.map((panel, index) => ({ ...panel, box: boxes[index] })), repaired: true }
}

function bubbleType(delivery: string): BubbleEdit['bubble_type'] {
  const value = delivery.toLocaleLowerCase()
  if (/thought|inner|suy nghĩ|nội tâm/.test(value)) return 'thought'
  if (/whisper|quiet|thì thầm/.test(value)) return 'whisper'
  if (/shout|yell|scream|hét/.test(value)) return 'shout'
  return 'speech'
}

function buildLocalEditor(result: MangaResult): EpisodeEdit {
  return {
    id: result.episode_id || 'local', revision: 1, status: 'draft',
    editor: { pages: result.story.pages.map((storyPage) => {
      const layoutPage = result.layout.pages.find((item) => item.page_number === storyPage.page_number)
      const safe = safePageLayout(layoutPage?.panels ?? [])
      return { page_number: storyPage.page_number, panels: safe.panels.map((panel) => {
        const storyPanel = storyPage.panels.find((item) => item.panel_id === panel.panel_id)
        return {
          panel_id: panel.panel_id, box: panel.box, reading_order: panel.reading_order,
          artwork_locked: false, panel_locked: false, status: 'draft' as const,
          bubbles: [
            ...(storyPanel?.dialogue || []).map((line, index) => ({
            bubble_id: `${panel.panel_id}_bubble_${index + 1}`, speaker: line.speaker, text: line.text,
            delivery: line.delivery, bubble_type: bubbleType(line.delivery),
            box: { x: Math.max(.05, .68 - index * .2), y: .06 + index * .16, width: .27, height: .13 },
            reading_order: index + 1, locked: false,
            })),
            ...(storyPanel?.narration ? [{ bubble_id: `${panel.panel_id}_caption_1`, text: storyPanel.narration, delivery: 'narration', bubble_type: 'caption' as const, box: { x: .05, y: .05, width: .42, height: .1 }, reading_order: (storyPanel?.dialogue.length || 0) + 1, locked: false }] : []),
            ...(storyPanel?.sound_effects || []).map((text, index) => ({ bubble_id: `${panel.panel_id}_sfx_${index + 1}`, text, delivery: 'sound effect', bubble_type: 'sfx' as const, box: { x: .06, y: Math.min(.82, .7 + index * .1), width: .28, height: .12 }, reading_order: (storyPanel?.dialogue.length || 0) + (storyPanel?.narration ? 2 : 1) + index, locked: false })),
          ],
        }
      }) }
    }) },
  }
}

export function StoryboardDesk({ result, episode: sharedEpisode, onEpisode, page, onPage }: {
  result: MangaResult; episode: EpisodeEdit; onEpisode: (episode: EpisodeEdit) => void
  page: number; onPage: (page: number) => void
}) {
  const [episode, setEpisode] = useState<EpisodeEdit>(sharedEpisode)
  const [activePanelId, setActivePanelId] = useState(result.story.pages[0]?.panels[0]?.panel_id || '')
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  useEffect(() => setEpisode(sharedEpisode), [sharedEpisode])

  useEffect(() => {
    if (!result.episode_id) return
    void fetch(`${API_BASE}/story-episodes/${result.episode_id}`).then(async (response) => {
      if (!response.ok) throw new Error('Không tải được dữ liệu biên tập')
      setEpisode(await response.json())
    }).catch(() => setSaveState('error'))
  }, [result.episode_id])

  const storyPage = result.story.pages.find((item) => item.page_number === page) || result.story.pages[0]
  const editPage = episode.editor.pages.find((item) => item.page_number === storyPage.page_number) || episode.editor.pages[0]
  const activePanel = editPage?.panels.find((item) => item.panel_id === activePanelId) || editPage?.panels[0]

  const updatePanel = (change: (panel: PanelEdit) => PanelEdit) => {
    if (!activePanel) return
    setEpisode((current) => {
      const next = { ...current, editor: { ...current.editor, pages: current.editor.pages.map((item) => item.page_number !== editPage.page_number ? item : { ...item, panels: item.panels.map((panel) => panel.panel_id === activePanel.panel_id ? change(panel) : panel) }) } }
      onEpisode(next)
      return next
    })
    setSaveState('idle')
  }
  const setBoxValue = (key: keyof PanelEdit['box'], value: number) => updatePanel((panel) => {
    const limits = { x: 1 - panel.box.width, y: 1 - panel.box.height, width: 1 - panel.box.x, height: 1 - panel.box.y }
    return { ...panel, box: { ...panel.box, [key]: Math.max(key === 'width' || key === 'height' ? .05 : 0, Math.min(limits[key], value)) } }
  })
  const updateBubble = (bubbleId: string, change: (bubble: BubbleEdit) => BubbleEdit) => updatePanel((panel) => ({ ...panel, bubbles: panel.bubbles.map((bubble) => bubble.bubble_id === bubbleId ? change(bubble) : bubble) }))
  const addBubble = () => updatePanel((panel) => ({ ...panel, bubbles: [...panel.bubbles, { bubble_id: `${panel.panel_id}_bubble_${Date.now()}`, text: '', delivery: 'normal', bubble_type: 'speech', box: { x: .58, y: .08, width: .32, height: .14 }, reading_order: panel.bubbles.length + 1, locked: false }] }))
  const save = async () => {
    if (!result.episode_id) { setSaveState('saved'); return }
    setSaveState('saving')
    try {
      const response = await fetch(`${API_BASE}/story-episodes/${result.episode_id}/editor`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_revision: episode.revision, pages: episode.editor.pages, status: episode.status }),
      })
      if (!response.ok) throw new Error((await response.json()).detail || 'Không lưu được')
      const saved = await response.json(); setEpisode(saved); onEpisode(saved); setSaveState('saved')
    } catch { setSaveState('error') }
  }

  return <div className="desk storyboard-desk">
    <div className="desk-title"><div><p className="eyebrow">EDITABLE STORYBOARD · RIGHT TO LEFT</p><h3>Trang {storyPage.page_number}</h3></div><div className="page-tabs">{result.story.pages.map((item) => <button className={item.page_number === storyPage.page_number ? 'active' : ''} onClick={() => onPage(item.page_number)} key={item.page_number}>{item.page_number}</button>)}</div></div>
    <div className="storyboard-toolbar"><div><strong>{storyPage.purpose}</strong><span>Tranh, panel và bong bóng là các lớp độc lập</span></div><button className="editor-save" onClick={() => void save()} disabled={saveState === 'saving'}><Check size={14} /> {saveState === 'saving' ? 'Đang lưu…' : saveState === 'saved' ? 'Đã lưu' : saveState === 'error' ? 'Lưu lại' : 'Lưu bố cục'}</button></div>
    <div className="editor-grid">
      <div className="page-preview-wrap"><span className="page-edge-label">TRANG {storyPage.page_number}</span><div className="manga-page">{editPage?.panels.map((panel) => { const storyPanel = storyPage.panels.find((item) => item.panel_id === panel.panel_id); return <button type="button" className={`layout-box editable-panel ${panel.panel_id === activePanel?.panel_id ? 'selected' : ''}`} key={panel.panel_id} onClick={() => setActivePanelId(panel.panel_id)} style={{ left: `${panel.box.x * 100}%`, top: `${panel.box.y * 100}%`, width: `${panel.box.width * 100}%`, height: `${panel.box.height * 100}%` }}><strong>{panel.reading_order}</strong><span>{storyPanel?.action}</span>{panel.bubbles.map((bubble) => <i className={`bubble-preview ${bubble.bubble_type}`} key={bubble.bubble_id} style={{ left: `${bubble.box.x * 100}%`, top: `${bubble.box.y * 100}%`, width: `${bubble.box.width * 100}%`, height: `${bubble.box.height * 100}%` }}>{bubble.text || '…'}</i>)}</button> })}</div></div>
      {activePanel && <aside className="panel-editor"><div className="panel-editor-head"><div><p className="eyebrow">PANEL LAYER</p><h3>{activePanel.panel_id}</h3></div><label className="lock-toggle"><input type="checkbox" checked={activePanel.panel_locked} onChange={(event) => updatePanel((panel) => ({ ...panel, panel_locked: event.target.checked, status: event.target.checked ? 'locked' : 'draft' }))} /> Khóa</label></div>
        <div className="coordinate-grid">{(['x', 'y', 'width', 'height'] as const).map((key) => <label key={key}><span>{key}</span><input type="number" min="0" max="1" step="0.01" disabled={activePanel.panel_locked} value={activePanel.box[key]} onChange={(event) => setBoxValue(key, Number(event.target.value))} /></label>)}</div>
        <label className="art-lock"><input type="checkbox" checked={activePanel.artwork_locked} onChange={(event) => updatePanel((panel) => ({ ...panel, artwork_locked: event.target.checked }))} /> Khóa tranh khi AI sửa lại panel</label>
        <div className="bubble-title"><strong>Bong bóng thoại</strong><button onClick={addBubble} disabled={activePanel.panel_locked}><Plus size={13} /> Thêm</button></div>
        <div className="bubble-editor-list">{activePanel.bubbles.map((bubble) => <section key={bubble.bubble_id}><div className="bubble-row"><input placeholder="Người nói" value={bubble.speaker || ''} disabled={bubble.locked || activePanel.panel_locked} onChange={(event) => updateBubble(bubble.bubble_id, (item) => ({ ...item, speaker: event.target.value }))} /><select value={bubble.bubble_type} disabled={bubble.locked || activePanel.panel_locked} onChange={(event) => updateBubble(bubble.bubble_id, (item) => ({ ...item, bubble_type: event.target.value as BubbleEdit['bubble_type'] }))}><option value="speech">Thoại</option><option value="thought">Suy nghĩ</option><option value="whisper">Thì thầm</option><option value="shout">Hét</option><option value="caption">Dẫn truyện</option><option value="sfx">Hiệu ứng</option></select></div><textarea value={bubble.text} disabled={bubble.locked || activePanel.panel_locked} onChange={(event) => updateBubble(bubble.bubble_id, (item) => ({ ...item, text: event.target.value }))} /><div className="coordinate-grid bubble-coordinates">{(['x', 'y', 'width', 'height'] as const).map((key) => <label key={key}><span>{key}</span><input type="number" min="0" max="1" step="0.01" disabled={bubble.locked || activePanel.panel_locked} value={bubble.box[key]} onChange={(event) => updateBubble(bubble.bubble_id, (item) => { const limits = { x: 1 - item.box.width, y: 1 - item.box.height, width: 1 - item.box.x, height: 1 - item.box.y }; const value = Number(event.target.value); return { ...item, box: { ...item.box, [key]: Math.max(key === 'width' || key === 'height' ? .03 : 0, Math.min(limits[key], value)) } } })} /></label>)}</div><div className="bubble-actions"><label><input type="checkbox" checked={bubble.locked} onChange={(event) => updateBubble(bubble.bubble_id, (item) => ({ ...item, locked: event.target.checked }))} /> Khóa lời</label><button disabled={bubble.locked || activePanel.panel_locked} onClick={() => updatePanel((panel) => ({ ...panel, bubbles: panel.bubbles.filter((item) => item.bubble_id !== bubble.bubble_id) }))}>Xóa</button></div></section>)}</div>
      </aside>}
    </div>
  </div>
}

function ArtworkDesk({ result, episode, onEpisode, selected, onSelect }: {
  result: MangaResult; episode: EpisodeEdit; onEpisode: (episode: EpisodeEdit) => void
  selected: string | null; onSelect: (panel: string) => void
}) {
  const [rendering, setRendering] = useState(false)
  const [renderError, setRenderError] = useState<string | null>(null)
  const renderOutput = episode.render || result.render
  const prompt = result.generation.panels.find((item) => item.panel_id === selected) || result.generation.panels[0]
  const rerender = async (panelIds?: string[]) => {
    if (!result.episode_id) return
    setRendering(true); setRenderError(null)
    try {
      const response = await fetch(`${API_BASE}/story-episodes/${result.episode_id}/rerender`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_revision: episode.revision, mode: 'comfyui', panel_ids: panelIds }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Không dựng được ảnh thật')
      onEpisode(payload)
    } catch (error) { setRenderError(error instanceof Error ? error.message : 'ComfyUI gặp lỗi') }
    finally { setRendering(false) }
  }
  const bubblesFor = (panelId: string) => episode.editor.pages.flatMap((page) => page.panels).find((panel) => panel.panel_id === panelId)?.bubbles || []
  return <div className="desk"><div className="desk-title"><div><p className="eyebrow">RENDER GALLERY</p><h3>Tranh manga & lời thoại</h3></div><div className="render-actions"><span className={`backend-badge ${renderOutput.backend}`}>{renderOutput.backend.toUpperCase()}</span>{result.episode_id && selected && <button className="panel-rerender" onClick={() => void rerender([selected])} disabled={rendering}><RefreshCw size={14} /> {rendering ? 'Đang dựng…' : 'Dựng lại panel'}</button>}{result.episode_id && <button onClick={() => void rerender()} disabled={rendering}><WandSparkles size={14} /> Dựng lại tất cả</button>}</div></div>{renderOutput.backend === 'mock' && <div className="mock-notice"><ImageIcon size={17} /><span><strong>Đây chỉ là ảnh MOCK kiểm tra kỹ thuật.</strong> Chọn một panel để dựng bằng Animagine XL hoặc dựng toàn bộ trang. Lời thoại được ghép rõ nét ở lớp riêng.</span></div>}{renderError && <div className="warning danger"><X size={17} /><span><strong>Render thất bại</strong>{renderError}</span></div>}<div className="artwork-grid"><div className="gallery-grid">{renderOutput.panels.map((panel) => <button key={panel.panel_id} className={selected === panel.panel_id ? 'active' : ''} onClick={() => onSelect(panel.panel_id)}>{panel.image_url ? <div className="artwork-canvas"><img src={`${API_BASE}${panel.image_url}`} alt={panel.panel_id} />{bubblesFor(panel.panel_id).map((bubble) => <i key={bubble.bubble_id} className={`artwork-bubble ${bubble.bubble_type}`} style={{ left: `${bubble.box.x * 100}%`, top: `${bubble.box.y * 100}%`, width: `${bubble.box.width * 100}%`, minHeight: `${bubble.box.height * 100}%` }}>{bubble.speaker && <b>{bubble.speaker}</b>}{bubble.text}</i>)}</div> : <div className="no-render"><ImageIcon /><span>Prompt only</span></div>}<span><strong>{panel.panel_id}</strong><small>{panel.status}</small></span></button>)}</div>{prompt && <aside className="prompt-inspector"><p className="eyebrow">SELECTED PROMPT</p><h3>{prompt.panel_id}</h3><label>Positive prompt</label><p>{prompt.positive_prompt}</p><label>Composition</label><p>{prompt.composition_control}</p><div className="parameter-row"><span>{prompt.parameters.width}×{prompt.parameters.height}</span><span>{prompt.parameters.steps} steps</span><span>CFG {prompt.parameters.cfg_scale}</span></div></aside>}</div></div>
}

function ReviewDesk({ result }: { result: MangaResult }) {
  return <div className="desk"><section className="review-summary"><div className="score-ring"><strong>{result.critique.overall_score.toFixed(1)}</strong><span>/10</span></div><div><p className="eyebrow">AI ART DIRECTOR</p><h2>{result.critique.decision.replaceAll('_', ' ')}</h2><p>{result.critique.summary}</p></div></section><div className="desk-title"><div><p className="eyebrow">PANEL REVIEW</p><h3>Kiểm tra từng panel</h3></div></div><div className="critique-list">{result.critique.panel_critiques.map((item) => <article key={item.panel_id}><span className={item.score >= 8 ? 'good' : 'warn'}>{item.score.toFixed(1)}</span><div><h4>{item.panel_id}</h4><p>{item.strengths.join(' · ')}</p>{item.issues.length > 0 && <small>Cần chú ý: {item.issues.join(' · ')}</small>}{item.correction && <blockquote>{item.correction}</blockquote>}</div></article>)}</div></div>
}

function ExportDesk({ result, episode }: { result: MangaResult; episode: EpisodeEdit }) {
  const download = () => { const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `${result.story.title.replaceAll(' ', '-').toLowerCase()}.json`; link.click(); URL.revokeObjectURL(url) }
  const publication = episode.render?.publication || result.render.publication
  const pages = episode.render?.pages || result.render.pages || []
  return <div className="desk export-desk"><div className="export-icon"><Boxes size={38} /></div><p className="eyebrow">PRODUCTION PACKAGE</p><h2>{publication ? 'Trang manga đã sẵn sàng' : 'Dự án đã sẵn sàng để hoàn thiện'}</h2><p>{publication ? 'Tranh, panel và lời thoại đã được ghép thành trang đọc hoàn chỉnh. Bạn có thể tải bản in PDF hoặc gói CBZ.' : 'Hãy dựng ảnh thật để hệ thống ghép panel và lời thoại thành trang hoàn chỉnh. Production JSON vẫn có thể tải ngay.'}</p>{pages.length > 0 && <div className="published-pages">{pages.map((page) => <img key={page.page_number} src={`${API_BASE}${page.image_url}`} alt={`Trang manga ${page.page_number}`} />)}</div>}<div className="export-actions">{publication && <><a className="primary" href={`${API_BASE}${publication.pdf_url}`} download><Download size={17} /> Tải PDF</a><a className="secondary" href={`${API_BASE}${publication.cbz_url}`} download><BookOpen size={17} /> Tải CBZ</a></>}<button className="secondary" onClick={download}><FileJson size={17} /> Production JSON</button></div><div className="export-manifest"><span><Check /> Kịch bản & nhịp truyện</span><span><Check /> Character bible</span><span><Check /> Bố cục trang</span><span><Check /> Bong bóng & lettering</span><span><Check /> Báo cáo chất lượng</span></div><details><summary>Xem dữ liệu thô</summary><pre>{JSON.stringify(result, null, 2)}</pre></details></div>
}

export default App
