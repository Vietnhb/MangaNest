import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock3,
  FolderOpen,
  Image as ImageIcon,
  Layers3,
  Library,
  Palette,
  Play,
  Plus,
  RefreshCw,
  Sparkles,
  Users,
  WandSparkles,
  Zap,
} from 'lucide-react'

interface DashboardSeries {
  id: string
  title: string
  episode_count: number
  premise?: string
  visual_style?: string
  updated_at?: string
}

interface DashboardStatus {
  status: string
  llm: { online: boolean; provider: string; model: string; free_only?: boolean }
  comfyui: { online: boolean }
  render_backend: string
  checkpoint: { name: string; ready: boolean }
}

const styles = [
  { id: 'cinematic', name: 'Cinematic Ink', note: 'Tương phản cao · khung hình điện ảnh', className: 'ink' },
  { id: 'shonen', name: 'Shōnen Motion', note: 'Nét động · hành động mạnh', className: 'shonen' },
  { id: 'shojo', name: 'Shōjo Bloom', note: 'Screentone mềm · cảm xúc', className: 'shojo' },
  { id: 'seinen', name: 'Noir Seinen', note: 'Bóng sâu · không khí trưởng thành', className: 'seinen' },
]

function relativeDate(value?: string) {
  if (!value) return 'Vừa cập nhật'
  const elapsed = Date.now() - new Date(value).getTime()
  const days = Math.floor(elapsed / 86_400_000)
  if (days <= 0) return 'Hôm nay'
  if (days === 1) return 'Hôm qua'
  return `${days} ngày trước`
}

export function Dashboard({ status, series, onCreate, onDemo, onOpen, onRefresh }: {
  status: DashboardStatus | null
  series: DashboardSeries[]
  onCreate: () => void
  onDemo: () => void
  onOpen: (seriesId: string) => void
  onRefresh: () => void
}) {
  const ready = Boolean(status?.llm.online && status?.comfyui.online && status?.checkpoint.ready)
  const episodeCount = series.reduce((sum, item) => sum + item.episode_count, 0)

  return <main className="product-home">
    <section className="home-hero">
      <div className="hero-copy">
        <span className="hero-kicker"><Sparkles size={14} /> AI MANGA CREATION SUITE</span>
        <h1>Từ ý tưởng đến<br /><em>trang manga hoàn chỉnh.</em></h1>
        <p>Viết cốt truyện, khóa thiết kế nhân vật, tạo storyboard, dựng tranh bằng Animagine XL và xuất bản — trong một studio duy nhất.</p>
        <div className="hero-actions">
          <button className="hero-primary" onClick={onCreate}><Plus size={18} /> Tạo manga mới <ArrowRight size={17} /></button>
          <button className="hero-secondary" onClick={onDemo}><Play size={17} /> Khám phá dự án mẫu</button>
        </div>
        <div className="hero-proof">
          <span><CheckCircle2 /> Nhân vật nhất quán</span>
          <span><CheckCircle2 /> Lettering tách lớp</span>
          <span><CheckCircle2 /> {episodeCount > 0 ? `${episodeCount} tập đã lưu` : 'PDF & CBZ'}</span>
        </div>
      </div>
      <div className="hero-art" aria-hidden="true">
        <div className="hero-page">
          <div className="hero-panel hero-panel-main"><span>01</span><i /></div>
          <div className="hero-panel hero-panel-small"><span>02</span><b>Đừng mở nó!</b></div>
          <div className="hero-panel hero-panel-small second"><span>03</span><i /></div>
        </div>
        <div className="floating-card character-float"><Users size={17} /><span><strong>Identity Lock</strong>2 nhân vật đã khóa</span></div>
        <div className="floating-card render-float"><Zap size={17} /><span><strong>Animagine XL</strong>Production ready</span></div>
      </div>
    </section>

    <section className="engine-strip">
      <div><span className={ready ? 'engine-dot ready' : 'engine-dot'} /><div><small>PRODUCTION ENGINE</small><strong>{ready ? 'Sẵn sàng sáng tác' : 'Cần kiểm tra dịch vụ'}</strong></div></div>
      <div className="engine-services">
        <span className={status?.llm.online ? 'ready' : ''}><WandSparkles /> {status?.llm.provider === 'openrouter' ? 'OpenRouter Free AI' : 'Local Story AI'}</span>
        <span className={status?.comfyui.online ? 'ready' : ''}><ImageIcon /> ComfyUI</span>
        <span className={status?.checkpoint.ready ? 'ready' : ''}><Layers3 /> Animagine XL 4.0</span>
      </div>
      <button onClick={onRefresh} aria-label="Làm mới trạng thái"><RefreshCw size={16} /></button>
    </section>

    <section className="home-section recent-section" id="projects">
      <div className="home-section-head"><div><span className="section-icon"><FolderOpen /></span><div><p>YOUR LIBRARY</p><h2>Dự án gần đây</h2></div></div><button onClick={onCreate}>Xem tất cả <ArrowRight size={15} /></button></div>
      {series.length > 0 ? <div className="project-grid">
        {series.slice(0, 4).map((item, index) => <button className="project-card" key={item.id} onClick={() => onOpen(item.id)}>
          <div className={`project-cover cover-${index % 4}`}><span>{String(index + 1).padStart(2, '0')}</span><i>漫</i><small>{item.visual_style || 'MANGA SERIES'}</small></div>
          <div className="project-card-copy"><span className="project-status">ĐANG SẢN XUẤT</span><h3>{item.title}</h3><p>{item.premise || 'Tiếp tục phát triển câu chuyện và thế giới nhân vật.'}</p><footer><span><BookOpen /> {item.episode_count} tập</span><span><Clock3 /> {relativeDate(item.updated_at)}</span></footer></div>
        </button>)}
        <button className="new-project-card" onClick={onCreate}><span><Plus /></span><strong>Bắt đầu thế giới mới</strong><small>Tạo story bible và tập đầu tiên</small></button>
      </div> : <div className="empty-library"><span><Library /></span><h3>Thư viện của bạn đang chờ câu chuyện đầu tiên</h3><p>Mỗi manga sẽ được lưu thành một series có character bible và continuity riêng.</p><button onClick={onCreate}><Plus size={16} /> Tạo dự án đầu tiên</button></div>}
    </section>

    <section className="home-section" id="styles">
      <div className="home-section-head"><div><span className="section-icon"><Palette /></span><div><p>STYLE DISCOVERY</p><h2>Phong cách được tuyển chọn</h2></div></div><span className="section-meta">Tối ưu cho Animagine XL</span></div>
      <div className="style-gallery">{styles.map((style, index) => <button key={style.id} className={`style-card ${style.className}`} onClick={onCreate}><div className="style-visual"><i /><b>{String(index + 1).padStart(2, '0')}</b></div><span><strong>{style.name}</strong><small>{style.note}</small></span><ArrowRight /></button>)}</div>
    </section>

    <section className="workflow-banner">
      <div><p>ONE CONNECTED WORKFLOW</p><h2>Một studio. Toàn bộ quy trình.</h2></div>
      <ol><li><span>01</span>Story</li><li><span>02</span>Characters</li><li><span>03</span>Storyboard</li><li><span>04</span>Artwork</li><li><span>05</span>Lettering</li><li><span>06</span>Publish</li></ol>
    </section>
  </main>
}
