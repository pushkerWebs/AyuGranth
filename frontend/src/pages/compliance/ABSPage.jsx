import { useMemo, useState } from 'react';
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleAlert,
  FileText,
  FlaskConical,
  Globe2,
  Leaf,
  Briefcase,
  Scale,
  ScrollText,
  Sparkles,
  Shield,
  ShieldAlert,
  Tag,
  X,
} from 'lucide-react';
import { cn } from '../../lib/utils/cn';
import Navbar from '../../components/Navbar';
import { complianceApi } from '../../api';

const AREA_ORDER = [
  'COMPETENT AUTHORITY',
  'APPROVAL / INTIMATION',
  'BENEFIT-SHARING',
  'IPR / DISCLOSURE',
  'REQUIRED DOCUMENTATION',
];

const STATUS_STYLES = {
  RELEVANT: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  'POTENTIALLY APPLICABLE': 'bg-amber-50 text-amber-800 border-amber-200',
  'NOT CLEARLY TRIGGERED': 'bg-slate-50 text-slate-700 border-slate-200',
  'INFORMATION REQUIRED': 'bg-orange-50 text-orange-800 border-orange-200',
  'NOT IDENTIFIED': 'bg-slate-50 text-slate-600 border-slate-200',
};

function statusClass(status) {
  return STATUS_STYLES[status] || STATUS_STYLES['INFORMATION REQUIRED'];
}

function formatSourceCount(evidenceList) {
  if (!evidenceList || !evidenceList.length) return '';
  const uniqueDocCount = new Set(evidenceList.map((e) => e.document || e.source || 'Retrieved source')).size;
  const passageCount = evidenceList.length;
  const sourceLabel = `${uniqueDocCount} unique source${uniqueDocCount === 1 ? '' : 's'}`;
  const passageLabel = `${passageCount} supporting passage${passageCount === 1 ? '' : 's'}`;
  return `${sourceLabel} · ${passageLabel}`;
}

function groupEvidenceBySource(evidenceList) {
  if (!evidenceList || !evidenceList.length) return [];
  const map = new Map();
  for (const item of evidenceList) {
    const key = item.document || item.source || 'Retrieved source';
    if (!map.has(key)) {
      map.set(key, {
        document: key,
        evidence_type: item.evidence_type,
        verified: item.verified,
        passages: [],
      });
    }
    const group = map.get(key);
    group.passages.push(item);
  }
  return Array.from(map.values());
}

function PassageItem({ item, index, total, compact }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className={cn('py-3 first:pt-0 last:pb-0', compact && 'py-2.5')}>
      <div className="flex items-center justify-between gap-2 text-[11px] text-[#161412]/55 mb-1.5">
        <span className="font-semibold text-[#176B45]">
          {total > 1 ? `Passage ${index + 1}` : 'Supporting excerpt'}
          {item.section ? ` · Section ${item.section}` : ''}
          {item.page ? ` · Page ${item.page}` : ''}
        </span>
        {item.verified && (
          <span className="shrink-0 rounded-full bg-emerald-50 border border-emerald-200 px-2 py-0.5 text-[9px] font-semibold text-emerald-700">
            Verified ID
          </span>
        )}
      </div>
      <p className={cn('text-xs leading-relaxed text-[#161412]/75', !expanded && 'line-clamp-3')}>
        {item.excerpt || 'No excerpt was returned for this source.'}
      </p>
      {item.relevance && (
        <p className="mt-2 text-[11px] leading-relaxed text-[#161412]/60">
          <span className="font-semibold text-[#161412]/75">Why it matters:</span> {item.relevance}
        </p>
      )}
      {item.excerpt && item.excerpt.length > 240 && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-[#176B45] hover:underline"
        >
          <span>{expanded ? 'Show less' : 'Read full excerpt'}</span>
          {expanded ? (
            <ChevronUp className="h-3.5 w-3.5 shrink-0" aria-hidden="true" focusable="false" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 shrink-0" aria-hidden="true" focusable="false" />
          )}
        </button>
      )}
    </div>
  );
}

function GroupedEvidenceCard({ group, compact = false }) {
  return (
    <article className={cn('rounded-xl border border-[#161412]/10 bg-[#fbfcfa] p-4', compact && 'p-3.5')}>
      <div className="flex items-start justify-between gap-4 border-b border-[#161412]/10 pb-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-[#176B45]">
            <BookOpen className="h-3.5 w-3.5 shrink-0" aria-hidden="true" focusable="false" />
            {group.evidence_type || 'Retrieved statutory evidence'}
          </div>
          <h4 className="mt-1.5 text-sm font-semibold text-[#161412] break-words" title={group.document}>
            {group.document}
          </h4>
        </div>
        <span className="shrink-0 rounded-full bg-[#176B45]/10 px-2.5 py-1 text-[10px] font-semibold text-[#176B45]">
          {group.passages.length} {group.passages.length === 1 ? 'passage' : 'passages'}
        </span>
      </div>

      <div className="mt-3 divide-y divide-[#161412]/10">
        {group.passages.map((passage, idx) => (
          <PassageItem
            key={passage.source_chunk_id || idx}
            item={passage}
            index={idx}
            total={group.passages.length}
            compact={compact}
          />
        ))}
      </div>
    </article>
  );
}

function ObligationCard({ item, index }) {
  const [expanded, setExpanded] = useState(false);
  const groupedEvidence = groupEvidenceBySource(item.evidence);
  return (
    <article className="flex h-full flex-col rounded-2xl border border-[#161412]/10 bg-white p-5 shadow-[0_8px_24px_rgba(34,55,43,0.04)] transition-shadow hover:shadow-[0_12px_30px_rgba(34,55,43,0.08)]">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#f4f6f3] font-mono text-xs font-semibold text-[#176B45]">{String(index + 1).padStart(2, '0')}</span>
          <h3 className="text-sm font-bold uppercase tracking-wide text-[#161412]">{item.area}</h3>
        </div>
        <span className={cn('rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider', statusClass(item.status))}>{item.status}</span>
      </div>
      <div className="mt-5 flex-1 space-y-4">
        <div><h4 className="label">What this means</h4><p className="body-copy">{item.what_this_means}</p></div>
        <div><h4 className="label">Next step</h4><p className="body-copy font-medium text-[#161412]">{item.next_step}</p></div>
        <div><h4 className="label">Why it matters</h4><p className="body-copy">{item.why_it_matters}</p></div>
      </div>
      {(item.details || item.evidence?.length) && (
        <div className="mt-5 border-t border-[#161412]/10 pt-4">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#176B45] hover:text-[#115234]"
          >
            <span>
              {expanded
                ? 'Hide supporting detail'
                : `View supporting detail${item.evidence?.length ? ` · ${formatSourceCount(item.evidence)}` : ''}`}
            </span>
            {expanded ? (
              <ChevronUp className="h-3.5 w-3.5 shrink-0" aria-hidden="true" focusable="false" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5 shrink-0" aria-hidden="true" focusable="false" />
            )}
          </button>
          {expanded && (
            <div className="mt-4 space-y-3">
              {item.details && <p className="rounded-lg bg-[#f4f6f3] p-3 text-xs leading-relaxed text-[#161412]/70">{item.details}</p>}
              {groupedEvidence.map((group) => (
                <GroupedEvidenceCard key={group.document} group={group} compact />
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  );
}

function ScreeningSummary({ result }) {
  const input = result.input_screening || {};
  const primaryFacts = [
    ['Ingredients', Array.isArray(input.ingredients) ? input.ingredients.join(', ') || 'Not provided' : input.ingredients],
    ['Source region', input.source_region],
    ['Biological origin', input.biological_origin],
    ['Category', input.category],
    ['Product / use', input.product_use],
    ['IP activity', input.ip_activity],
  ];
  const contextFacts = [
    ['Access / use context', input.access_use_context],
    ['Applicant / entity status', input.applicant_entity_status],
    ['Purpose', input.research_or_commercial_purpose],
    ['Traditional knowledge used', input.traditional_knowledge_used],
    ['Accessed from region', input.access_from_region],
    ['Procurement details', input.procurement_details],
    ['Existing permissions', input.existing_permissions],
  ];
  const hasContext = contextFacts.some(([, value]) => value && value !== 'Not provided');
  return (
    <section className="rounded-2xl border border-[#161412]/10 bg-white p-6 shadow-[0_8px_24px_rgba(34,55,43,0.04)]">
      <div className="mb-5 flex items-center justify-between gap-4 border-b border-[#161412]/10 pb-3">
        <div><p className="eyebrow">Input / screening criteria</p><p className="mt-1 text-xs text-[#161412]/55">The assessment below uses these submitted facts only.</p></div>
        <FileText className="h-5 w-5 text-[#176B45]" />
      </div>
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{primaryFacts.map(([label, value]) => <div key={label}><p className="label">{label}</p><p className={cn('text-sm font-medium', value === 'Not provided' ? 'text-[#161412]/45' : 'text-[#161412]')}>{value || 'Not provided'}</p></div>)}</div>
      {hasContext && (<><div className="my-5 border-t border-[#161412]/10 pt-3"><p className="eyebrow text-[#161412]/50">Optional case context</p></div><div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{contextFacts.map(([label, value]) => <div key={label}><p className="label">{label}</p><p className={cn('text-sm font-medium', value === 'Not provided' ? 'text-[#161412]/45' : 'text-[#161412]')}>{value || 'Not provided'}</p></div>)}</div></>)}
    </section>
  );
}

/* ─── Ingredient Tag Input ─────────────────────────────────────────────── */
function IngredientInput({ value, onChange }) {
  const [inputVal, setInputVal] = useState('');
  const tags = value ? value.split(',').map(t => t.trim()).filter(Boolean) : [];

  const addTag = (raw) => {
    const tag = raw.trim();
    if (!tag) return;
    const existing = tags.map(t => t.toLowerCase());
    if (existing.includes(tag.toLowerCase())) return;
    const newVal = [...tags, tag].join(', ');
    onChange({ target: { name: 'ingredients', value: newVal, type: 'text' } });
    setInputVal('');
  };

  const removeTag = (index) => {
    const newTags = tags.filter((_, i) => i !== index);
    onChange({ target: { name: 'ingredients', value: newTags.join(', '), type: 'text' } });
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addTag(inputVal);
    }
    if (e.key === 'Backspace' && !inputVal && tags.length > 0) {
      removeTag(tags.length - 1);
    }
  };

  return (
    <div className="group">
      <div className="flex items-center gap-2 mb-2">
        <Leaf className="h-4 w-4 text-[#176B45]" />
        <span className="text-sm font-semibold text-[#17211d]">Biological resources / ingredients</span>
        <span className="rounded bg-[#176B45]/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-[#176B45]">Required</span>
      </div>
      <div className={cn(
        'flex min-h-[56px] flex-wrap items-start gap-2 rounded-2xl border-2 bg-white px-4 py-3 transition-all duration-200',
        'border-[#dfe6e0] focus-within:border-[#176B45] focus-within:shadow-[0_0_0_4px_rgba(23,107,69,0.08)]',
      )}>
        {tags.map((tag, i) => (
          <span key={`${tag}-${i}`} className="inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-[#176B45]/10 to-[#2a9d6a]/10 px-3 py-1.5 text-xs font-semibold text-[#176B45] transition-all duration-150 hover:from-[#176B45]/15 hover:to-[#2a9d6a]/15">
            <Leaf className="h-3 w-3" />{tag}
            <button type="button" onClick={() => removeTag(i)} className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-[#176B45]/20"><X className="h-3 w-3" /></button>
          </span>
        ))}
        <input
          type="text"
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => addTag(inputVal)}
          placeholder={tags.length === 0 ? 'Type and press Enter (e.g. Ashwagandha)' : 'Add more...'}
          className="min-w-[140px] flex-1 bg-transparent py-1 text-sm text-[#17211d] outline-none placeholder:text-[#17211d]/30"
        />
      </div>
      <p className="mt-1.5 text-[11px] text-[#17211d]/45">Press Enter or comma to add each ingredient. Click the X to remove.</p>
    </div>
  );
}

/* ─── Premium Toggle Switch ────────────────────────────────────────────── */
function BiologicalToggle({ checked, onChange }) {
  return (
    <div className={cn(
      'group relative flex items-start gap-4 rounded-2xl border-2 p-5 transition-all duration-300 cursor-pointer select-none',
      checked ? 'border-[#176B45]/30 bg-gradient-to-br from-[#176B45]/5 to-[#2a9d6a]/5' : 'border-[#dfe6e0] bg-[#fbfcfa] hover:border-[#b9c5bd]',
    )} onClick={() => onChange({ target: { name: 'is_biological', type: 'checkbox', checked: !checked } })}>
      <div className={cn(
        'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-all duration-300',
        checked ? 'bg-[#176B45] text-white shadow-[0_4px_12px_rgba(23,107,69,0.3)]' : 'bg-[#f4f6f3] text-[#849188]',
      )}>
        <Leaf className="h-5 w-5" />
      </div>
      <div className="flex-1">
        <div className="flex items-center gap-3">
          <span className="text-sm font-bold text-[#17211d]">Biological origin declared</span>
          <div className={cn(
            'relative h-6 w-11 rounded-full transition-all duration-300',
            checked ? 'bg-[#176B45]' : 'bg-[#cfdad1]',
          )}>
            <div className={cn(
              'absolute top-1 h-4 w-4 rounded-full bg-white shadow-sm transition-all duration-300',
              checked ? 'left-6' : 'left-1',
            )} />
          </div>
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-[#17211d]/55">
          {checked ? 'The submitted materials include biological resources. ABS screening will proceed.' : 'Uncheck only if the materials are purely synthetic. The screening will note this as a non-trigger.'}
        </p>
      </div>
      {checked && <Sparkles className="absolute right-4 top-4 h-4 w-4 text-[#176B45]/40" />}
    </div>
  );
}

/* ─── Collapsible Section ──────────────────────────────────────────────── */
function CollapsibleSection({ icon: Icon, title, subtitle, badge, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={cn(
      'rounded-2xl border-2 transition-all duration-300 overflow-hidden',
      open ? 'border-[#176B45]/20 bg-white shadow-[0_8px_32px_rgba(23,107,69,0.04)]' : 'border-[#dfe6e0] bg-[#fbfcfa] hover:border-[#b9c5bd]',
    )}>
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-4 px-6 py-5 text-left">
        <div className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-all duration-300',
          open ? 'bg-[#176B45] text-white shadow-[0_4px_12px_rgba(23,107,69,0.2)]' : 'bg-[#f4f6f3] text-[#849188]',
        )}>
          <Icon className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn('text-sm font-bold', open ? 'text-[#176B45]' : 'text-[#17211d]')}>{title}</span>
            {badge && <span className="rounded-full bg-[#176B45]/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-[#176B45]">{badge}</span>}
          </div>
          <p className="mt-0.5 text-xs text-[#17211d]/50">{subtitle}</p>
        </div>
        <ChevronDown className={cn('h-5 w-5 shrink-0 text-[#849188] transition-transform duration-300', open && 'rotate-180')} />
      </button>
      <div className={cn('transition-all duration-300 ease-in-out', open ? 'max-h-[1200px] opacity-100' : 'max-h-0 opacity-0')}>
        <div className="border-t border-[#dfe6e0] px-6 pb-6 pt-5 space-y-5">
          {children}
        </div>
      </div>
    </div>
  );
}

/* ─── Progress Bar ─────────────────────────────────────────────────────── */
function FormProgress({ formData }) {
  const fields = [
    formData.ingredients,
    formData.source_region,
    formData.category,
    formData.product_use,
    formData.access_use_context,
    formData.applicant_entity_status,
    formData.research_or_commercial_purpose,
    formData.ip_activity,
  ];
  const filled = fields.filter(f => f && f.trim()).length;
  const pct = Math.round((filled / fields.length) * 100);
  return (
    <div className="flex items-center gap-4">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#e8ede9]">
        <div className="h-full rounded-full bg-gradient-to-r from-[#176B45] to-[#2a9d6a] transition-all duration-500 ease-out" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-semibold text-[#176B45]">{filled}/{fields.length}</span>
    </div>
  );
}

/* ─── Enhanced Field Components ────────────────────────────────────────── */
function PremiumField({ label, hint, name, value, onChange, placeholder, multiline = false, icon: Icon }) {
  const Component = multiline ? 'textarea' : 'input';
  return (
    <label className="group block">
      <div className="mb-2 flex items-center gap-2">
        {Icon && <Icon className="h-3.5 w-3.5 text-[#849188] transition-colors group-focus-within:text-[#176B45]" />}
        <span className="text-sm font-semibold text-[#17211d]">{label}</span>
      </div>
      {hint && <span className="mb-2 block text-[11px] text-[#17211d]/45">{hint}</span>}
      <Component
        name={name}
        value={value || ''}
        onChange={onChange}
        placeholder={placeholder}
        rows={multiline ? 3 : undefined}
        className="w-full rounded-xl border-2 border-[#e4e9e5] bg-white px-4 py-3 text-sm text-[#17211d] outline-none transition-all duration-200 placeholder:text-[#17211d]/25 focus:border-[#176B45] focus:shadow-[0_0_0_4px_rgba(23,107,69,0.08)]"
      />
    </label>
  );
}

function PremiumSelect({ label, name, value, onChange, icon: Icon }) {
  return (
    <label className="group block">
      <div className="mb-2 flex items-center gap-2">
        {Icon && <Icon className="h-3.5 w-3.5 text-[#849188] transition-colors group-focus-within:text-[#176B45]" />}
        <span className="text-sm font-semibold text-[#17211d]">{label}</span>
      </div>
      <select
        name={name}
        value={value === null ? '' : String(value)}
        onChange={onChange}
        className="w-full rounded-xl border-2 border-[#e4e9e5] bg-white px-4 py-3 text-sm text-[#17211d] outline-none transition-all duration-200 focus:border-[#176B45] focus:shadow-[0_0_0_4px_rgba(23,107,69,0.08)]"
      >
        <option value="">Not provided</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    </label>
  );
}

/* ─── Main ABSPage ─────────────────────────────────────────────────────── */
export default function ABSPage() {
  const [formData, setFormData] = useState({
    ingredients: '', source_region: '', is_biological: true, category: '', product_use: '', access_use_context: '', applicant_entity_status: '', research_or_commercial_purpose: '', traditional_knowledge_used: null, ip_activity: '', access_from_region: null, procurement_details: '', existing_permissions: '',
  });
  const [stage, setStage] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleChange = (event) => {
    const { name, value, type, checked } = event.target;
    setFormData((previous) => ({ ...previous, [name]: type === 'checkbox' ? checked : value }));
  };
  const handleSelectChange = (event) => setFormData((previous) => ({ ...previous, [event.target.name]: event.target.value === '' ? null : event.target.value === 'true' }));
  const resetFlow = () => { setStage(0); setResult(null); setError(null); };

  const handleScreening = async (event) => {
    event.preventDefault();
    if (!formData.ingredients.trim()) { setError('Add at least one biological resource or ingredient to begin.'); return; }
    setStage(1); setError(null); setResult(null);
    try {
      const payload = { ...formData, ingredients: formData.ingredients.split(',').map((item) => item.trim()).filter(Boolean), source_region: formData.source_region.trim() || null, category: formData.category.trim() || null, product_use: formData.product_use.trim() || null, access_use_context: formData.access_use_context.trim() || null, applicant_entity_status: formData.applicant_entity_status.trim() || null, research_or_commercial_purpose: formData.research_or_commercial_purpose.trim() || null, ip_activity: formData.ip_activity.trim() || null, procurement_details: formData.procurement_details.trim() || null, existing_permissions: formData.existing_permissions.trim() || null };
      const response = await complianceApi.screenABS(payload);
      setResult(response); setStage(2);
    } catch (err) { console.error(err); setError('Failed to complete the ABS assessment. Please check that the backend is running and try again.'); setStage(0); }
  };

  const obligations = useMemo(() => {
    const items = result?.obligations || [];
    return [...items].sort((a, b) => AREA_ORDER.indexOf(a.area) - AREA_ORDER.indexOf(b.area));
  }, [result]);

  return (
    <div className="abs-page min-h-screen bg-[#f4f6f3] pb-20 font-sans text-[#17211d]">
      <Navbar />
      <main className="mx-auto flex max-w-6xl flex-col items-center px-4 pb-10 pt-28 sm:px-6">
        {/* ─── Header ──────────────────────────────────────────────── */}
        <header className="mb-10 max-w-3xl text-center">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-[#176B45]/10 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-[#176B45]">
            <Shield className="h-3.5 w-3.5" /> Access & Benefit Sharing
          </div>
          <h1 className="font-serif text-4xl text-[#17211d] md:text-5xl">ABS Duties</h1>
          <p className="mx-auto mt-4 max-w-2xl text-sm leading-relaxed text-[#17211d]/60">
            Screen the facts that may shape an Access and Benefit Sharing pathway, then review the evidence and information gaps before taking action.
          </p>
        </header>

        {/* ─── Step Indicator ──────────────────────────────────────── */}
        <div className="mb-10 flex items-center gap-0">
          <div className={cn('flex items-center gap-2.5 rounded-full border-2 px-5 py-2.5 transition-all duration-300', stage <= 1 ? 'border-[#176B45] bg-white text-[#176B45] shadow-[0_4px_16px_rgba(23,107,69,0.12)]' : 'border-[#dfe6e0] text-[#849188]')}>
            <span className={cn('flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold', stage <= 1 ? 'bg-[#176B45] text-white' : 'bg-[#e8ede9] text-[#849188]')}>1</span>
            <span className="text-[11px] font-bold uppercase tracking-wider">Screening</span>
          </div>
          <div className="flex items-center">
            <span className={cn('h-0.5 w-10 transition-colors duration-300', stage === 2 ? 'bg-[#176B45]' : 'bg-[#dfe6e0]')} />
            <span className={cn('h-2 w-2 rotate-45 border-r-2 border-t-2 -ml-1.5 transition-colors duration-300', stage === 2 ? 'border-[#176B45]' : 'border-[#dfe6e0]')} />
          </div>
          <div className={cn('flex items-center gap-2.5 rounded-full border-2 px-5 py-2.5 transition-all duration-300', stage === 2 ? 'border-[#176B45] bg-white text-[#176B45] shadow-[0_4px_16px_rgba(23,107,69,0.12)]' : 'border-[#dfe6e0] text-[#849188]')}>
            <span className={cn('flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold', stage === 2 ? 'bg-[#176B45] text-white' : 'bg-[#e8ede9] text-[#849188]')}>2</span>
            <span className="text-[11px] font-bold uppercase tracking-wider">Assessment</span>
          </div>
        </div>

        {error && <div className="mb-8 flex w-full max-w-4xl items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-red-700"><ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" /><p className="text-sm">{error}</p></div>}

        {/* ─── FORM (Stage 0) ──────────────────────────────────────── */}
        {stage === 0 && (
          <section className="w-full max-w-4xl">
            <form onSubmit={handleScreening} className="space-y-5">

              {/* ── Card: Essential Information ── */}
              <div className="rounded-2xl border-2 border-[#176B45]/20 bg-white p-6 shadow-[0_12px_40px_rgba(23,107,69,0.06)] md:p-8">
                <div className="mb-6 flex items-start justify-between gap-4 border-b border-[#e8ede9] pb-5">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#176B45] text-white shadow-[0_4px_12px_rgba(23,107,69,0.3)]">
                      <FlaskConical className="h-5 w-5" />
                    </div>
                    <div>
                      <h2 className="text-lg font-bold text-[#17211d]">Essential Information</h2>
                      <p className="text-xs text-[#17211d]/50">The minimum facts needed to begin an ABS screening.</p>
                    </div>
                  </div>
                  <FormProgress formData={formData} />
                </div>

                <div className="space-y-6">
                  <IngredientInput value={formData.ingredients} onChange={handleChange} />

                  <div className="grid gap-6 md:grid-cols-2">
                    <PremiumField
                      label="Source region"
                      hint="Leave blank if unknown — the result will flag this gap."
                      name="source_region"
                      value={formData.source_region}
                      onChange={handleChange}
                      placeholder="e.g. India, Brazil, Kenya"
                      icon={Globe2}
                    />
                    <PremiumField
                      label="Category"
                      name="category"
                      value={formData.category}
                      onChange={handleChange}
                      placeholder="e.g. herbal medicine, cosmetic, nutraceutical"
                      icon={Tag}
                    />
                  </div>

                  <BiologicalToggle checked={formData.is_biological} onChange={handleChange} />
                </div>
              </div>

              {/* ── Card: Resource & Product Details ── */}
              <CollapsibleSection
                icon={FlaskConical}
                title="Resource & Product Details"
                subtitle="Describe what the resource will be used for."
                badge="Optional"
                defaultOpen={false}
              >
                <PremiumField
                  label="Product / use information"
                  name="product_use"
                  value={formData.product_use}
                  onChange={handleChange}
                  placeholder="e.g. research extract, finished herbal product, dietary supplement"
                  multiline
                  icon={FlaskConical}
                />
                <PremiumField
                  label="Access / use context"
                  name="access_use_context"
                  value={formData.access_use_context}
                  onChange={handleChange}
                  placeholder="How will the resource be accessed or used?"
                  multiline
                  icon={ScrollText}
                />
              </CollapsibleSection>

              {/* ── Card: Applicant & Purpose ── */}
              <CollapsibleSection
                icon={Briefcase}
                title="Applicant & Purpose"
                subtitle="Who is applying and what is the intended activity?"
                badge="Optional"
                defaultOpen={false}
              >
                <div className="grid gap-5 md:grid-cols-2">
                  <PremiumField
                    label="Applicant / entity status"
                    name="applicant_entity_status"
                    value={formData.applicant_entity_status}
                    onChange={handleChange}
                    placeholder="e.g. individual, Indian company, foreign entity"
                    icon={Briefcase}
                  />
                  <PremiumField
                    label="Purpose"
                    name="research_or_commercial_purpose"
                    value={formData.research_or_commercial_purpose}
                    onChange={handleChange}
                    placeholder="e.g. research, commercial utilization"
                    icon={FlaskConical}
                  />
                </div>
                <div className="grid gap-5 md:grid-cols-2">
                  <PremiumField
                    label="Procurement details"
                    name="procurement_details"
                    value={formData.procurement_details}
                    onChange={handleChange}
                    placeholder="Source, supplier, collection details"
                    multiline
                    icon={ScrollText}
                  />
                  <PremiumField
                    label="Existing permissions / agreements"
                    name="existing_permissions"
                    value={formData.existing_permissions}
                    onChange={handleChange}
                    placeholder="Any existing permits, MTAs, or approvals"
                    multiline
                    icon={FileText}
                  />
                </div>
              </CollapsibleSection>

              {/* ── Card: Legal & IP Context ── */}
              <CollapsibleSection
                icon={Scale}
                title="Legal & IP Context"
                subtitle="Patent activity, traditional knowledge, and regional access."
                badge="Optional"
                defaultOpen={false}
              >
                <PremiumField
                  label="IP activity"
                  name="ip_activity"
                  value={formData.ip_activity}
                  onChange={handleChange}
                  placeholder="e.g. patent planned, patent filed IN12345, no IP activity"
                  multiline
                  icon={Scale}
                />
                <div className="grid gap-5 md:grid-cols-2">
                  <PremiumSelect
                    label="Associated traditional knowledge used?"
                    name="traditional_knowledge_used"
                    value={formData.traditional_knowledge_used}
                    onChange={handleSelectChange}
                    icon={BookOpen}
                  />
                  <PremiumSelect
                    label="Accessed from the stated region?"
                    name="access_from_region"
                    value={formData.access_from_region}
                    onChange={handleSelectChange}
                    icon={Globe2}
                  />
                </div>
              </CollapsibleSection>

              {/* ── Submit ── */}
              <button
                type="submit"
                className="group flex w-full items-center justify-center gap-3 rounded-2xl bg-gradient-to-r from-[#176B45] to-[#1d8254] py-4 text-base font-bold text-white shadow-[0_8px_24px_rgba(23,107,69,0.24)] transition-all duration-300 hover:shadow-[0_12px_32px_rgba(23,107,69,0.32)] hover:from-[#125537] hover:to-[#176B45] active:scale-[0.99]"
              >
                <Shield className="h-5 w-5 transition-transform duration-300 group-hover:scale-110" />
                Screen for ABS Considerations
                <ArrowRight className="h-5 w-5 transition-transform duration-300 group-hover:translate-x-1" />
              </button>

              <p className="text-center text-[11px] text-[#17211d]/40">
                Only the ingredients field is required. Optional context improves the precision of the assessment.
              </p>
            </form>
          </section>
        )}

        {/* ─── LOADING (Stage 1) ───────────────────────────────────── */}
        {stage === 1 && (
          <section className="flex min-h-[360px] w-full max-w-4xl flex-col items-center justify-center rounded-2xl border-2 border-[#dfe6e0] bg-white p-10 text-center shadow-[0_12px_40px_rgba(34,55,43,0.06)]">
            <div className="relative mb-6">
              <div className="h-14 w-14 animate-spin rounded-full border-4 border-[#e4f1e8] border-t-[#176B45]" />
              <Shield className="absolute left-1/2 top-1/2 h-5 w-5 -translate-x-1/2 -translate-y-1/2 text-[#176B45]/60" />
            </div>
            <h2 className="font-serif text-2xl text-[#17211d]">Building an evidence-grounded assessment</h2>
            <p className="mt-3 max-w-md text-sm leading-relaxed text-[#17211d]/55">Retrieving relevant ABS/statutory evidence and checking which facts are still missing.</p>
            <div className="mt-6 flex items-center gap-6 text-[11px] font-semibold text-[#849188]">
              <span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#176B45]" /> Querying corpus</span>
              <span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#176B45] [animation-delay:0.3s]" /> Matching evidence</span>
              <span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#176B45] [animation-delay:0.6s]" /> Assessing gaps</span>
            </div>
          </section>
        )}

        {/* ─── RESULTS (Stage 2) ───────────────────────────────────── */}
        {stage === 2 && result && <div className="w-full max-w-5xl space-y-7"><div className="flex flex-wrap items-center justify-between gap-4"><div><p className="eyebrow">Assessment complete</p><p className="mt-1 text-sm text-[#17211d]/55">Case-specific screening; not a legal opinion.</p></div><button onClick={resetFlow} className="rounded-lg border border-[#cfdad1] bg-white px-4 py-2 text-xs font-semibold text-[#17211d]/70 transition hover:border-[#176B45] hover:text-[#176B45]">Start over</button></div>
          <ScreeningSummary result={result} />
          <section className="rounded-2xl border border-[#dfe6e0] bg-white p-6 shadow-[0_8px_24px_rgba(34,55,43,0.04)] md:p-8"><div className="flex flex-wrap items-start justify-between gap-5"><div><p className="eyebrow">ABS assessment</p><div className="mt-2 flex items-center gap-3"><span className={cn('h-3 w-3 rounded-full', result.color === 'green' ? 'bg-emerald-500' : result.color === 'amber' ? 'bg-orange-400' : 'bg-amber-400')} /><h2 className="text-2xl font-bold tracking-tight text-[#17211d]">{result.overall_status}</h2></div></div><div className="rounded-xl border border-[#dfe6e0] bg-[#f4f6f3] px-4 py-3 text-right"><p className="label">Evidence confidence</p><p className="mt-1 text-sm font-bold text-[#176B45]">{result.confidence}</p></div></div><p className="mt-6 max-w-3xl text-sm font-medium leading-relaxed text-[#17211d]/75">{result.reasoning}</p><p className="mt-5 border-t border-[#dfe6e0] pt-4 text-[11px] text-[#17211d]/50">{result.disclaimer}</p></section>
          {result.key_findings?.length > 0 && <section className="rounded-2xl border border-[#dfe6e0] bg-white p-6 shadow-sm md:p-8"><p className="eyebrow">Key compliance / legal findings</p><div className="mt-5 grid gap-3 md:grid-cols-2">{result.key_findings.slice(0, 5).map((finding, index) => <div key={`${finding}-${index}`} className="flex gap-3 rounded-xl bg-[#f4f6f3] p-4"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#176B45]" /><p className="text-sm leading-relaxed text-[#17211d]/75">{finding}</p></div>)}</div></section>}
          {result.information_gaps?.length > 0 && <section className="rounded-2xl border border-orange-200 bg-orange-50/60 p-6 md:p-8"><div className="flex items-start gap-3"><CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-orange-700" /><div><p className="eyebrow text-orange-800">Information needed to finalize ABS pathway</p><p className="mt-2 text-sm leading-relaxed text-orange-900/75">These items are not inferred. Provide them only if they are relevant to the planned activity.</p><ul className="mt-4 grid gap-2 text-sm text-orange-950/80 md:grid-cols-2">{result.information_gaps.map((gap) => <li key={gap} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-orange-500" />{gap}</li>)}</ul></div></div></section>}
          <section><div className="mb-5 flex items-end justify-between gap-4"><div><p className="eyebrow">Obligation navigator</p><h2 className="mt-2 font-serif text-3xl text-[#17211d]">Five areas, assessed separately</h2></div><p className="hidden max-w-xs text-right text-xs leading-relaxed text-[#17211d]/50 sm:block">Statuses vary by available facts and retrieved evidence. No area is marked mandatory by default.</p></div><div className="grid gap-5 lg:grid-cols-2">{obligations.map((item, index) => <ObligationCard key={item.area} item={item} index={index} />)}</div></section>
          <section className="rounded-2xl border border-[#dfe6e0] bg-white p-6 shadow-sm md:p-8">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="eyebrow">Evidence / sources</p>
                <h2 className="mt-2 font-serif text-2xl text-[#17211d]">Retrieved support for this assessment</h2>
                {result.evidence?.length > 0 && (
                  <p className="mt-1 text-xs font-semibold text-[#176B45]">
                    {formatSourceCount(result.evidence)}
                  </p>
                )}
              </div>
              <BookOpen className="h-6 w-6 text-[#176B45]" aria-hidden="true" focusable="false" />
            </div>
            {result.evidence?.length ? (
              <div className="mt-5 space-y-4">
                {groupEvidenceBySource(result.evidence).map((group) => (
                  <GroupedEvidenceCard key={group.document} group={group} />
                ))}
              </div>
            ) : (
              <div className="mt-5 rounded-xl border border-dashed border-[#cfdad1] bg-[#f4f6f3] p-6 text-sm leading-relaxed text-[#17211d]/60">
                No reliable supporting ABS/statutory evidence was retrieved. This result deliberately does not fabricate citations or obligations.
              </div>
            )}
          </section>
          <div className="flex flex-col items-center gap-4 border-t border-[#dfe6e0] pt-8 text-center"><p className="max-w-2xl text-xs leading-relaxed text-[#17211d]/55">This screening is preliminary information, not legal advice. Confirm the applicable authority and pathway with qualified counsel or the relevant biodiversity authority before access, utilization, commercialization, or IP filing.</p><button onClick={resetFlow} className="inline-flex items-center gap-2 rounded-lg border border-[#cfdad1] bg-white px-5 py-2.5 text-xs font-semibold text-[#17211d]/70 transition hover:border-[#176B45] hover:text-[#176B45]"><span>Run another screening</span><ArrowRight className="h-3.5 w-3.5" aria-hidden="true" focusable="false" /></button></div>
        </div>}
      </main>
    </div>
  );
}


