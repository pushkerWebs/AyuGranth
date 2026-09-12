import { useState } from 'react';
import { ShieldCheck, Search, ArrowRight, CheckCircle2, CircleAlert, BookOpen, ChevronDown, ChevronUp } from 'lucide-react';
import { complianceApi } from '../../api';

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

function ObligationMini({ item }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-[#161412]/10 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h4 className="text-sm font-bold uppercase tracking-wide text-[#161412]">{item.area}</h4>
        <span className={`rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${statusClass(item.status)}`}>{item.status}</span>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-[#161412]/70">{item.what_this_means}</p>
      <p className="mt-2 text-xs font-medium text-[#161412]">{item.next_step}</p>
      {(item.details || item.evidence?.length > 0) && (
        <button onClick={() => setOpen(!open)} className="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-[#176B45]">
          {open ? 'Hide detail' : 'View detail'}
          {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      )}
      {open && (
        <div className="mt-3 space-y-2">
          {item.details && <p className="rounded-lg bg-[#f4f6f3] p-3 text-xs text-[#161412]/65">{item.details}</p>}
          {item.evidence?.map((ev) => (
            <div key={ev.source_chunk_id} className="rounded-lg border border-[#161412]/10 bg-[#fbfcfa] p-3 text-xs">
              <p className="font-semibold text-[#176B45]">{ev.document || ev.source}</p>
              {ev.section && <p className="text-[#161412]/50">Section {ev.section}</p>}
              <p className="mt-1 line-clamp-3 text-[#161412]/70">{ev.excerpt}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ABS() {
  const [ingredients, setIngredients] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!ingredients.trim()) return;

    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await complianceApi.screenABS({
        ingredients: ingredients.split(',').map(i => i.trim()),
      });
      setResult(response);
    } catch (err) {
      console.error(err);
      setError(err.response?.data?.detail || 'An error occurred during ABS screening.');
    } finally {
      setIsLoading(false);
    }
  };

  const obligations = result?.obligations || [];

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-serif text-[#176B45] mb-2 flex items-center justify-center gap-3">
          <ShieldCheck className="w-8 h-8" />
          Access & Benefit Sharing (ABS)
        </h1>
        <p className="text-[#161412]/60">Screen ingredients against ABS/statutory requirements with evidence-grounded assessment.</p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4 max-w-2xl mx-auto">
        <div className="relative">
          <textarea
            value={ingredients}
            onChange={(e) => setIngredients(e.target.value)}
            placeholder="Enter ingredients (e.g. Neem, Ashwagandha, Aloe Vera)..."
            rows={4}
            className="w-full bg-white border border-[#161412]/20 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-[#176B45] shadow-sm resize-none"
            required
          />
        </div>
        <button
          type="submit"
          disabled={isLoading || !ingredients.trim()}
          className="w-full py-3 bg-[#176B45] text-white font-medium rounded-xl hover:bg-[#125537] transition-colors disabled:opacity-50 flex justify-center items-center gap-2"
        >
          {isLoading ? <div className="w-5 h-5 rounded-full border-2 border-white border-t-transparent animate-spin" /> : <Search className="w-5 h-5" />}
          Screen for ABS Considerations
        </button>
        <p className="text-xs text-[#161412]/40 text-center">For a full screening with optional context fields, use the <a href="/abs" className="text-[#176B45] font-semibold underline">ABS Duties page</a>.</p>
      </form>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-xl text-center max-w-2xl mx-auto">
          {error}
        </div>
      )}

      {isLoading && (
        <div className="py-12 flex flex-col items-center justify-center">
          <div className="w-8 h-8 rounded-full border-2 border-[#176B45] border-t-transparent animate-spin mb-4" />
          <p className="text-[#161412]/60 font-medium">Building evidence-grounded ABS assessment...</p>
        </div>
      )}

      {result && (
        <div className="space-y-6 max-w-3xl mx-auto">
          {/* Overall Status */}
          <div className={`p-6 border rounded-xl ${
            result.color === 'green' ? 'bg-emerald-50 border-emerald-200' : result.color === 'amber' ? 'bg-orange-50 border-orange-200' : 'bg-amber-50 border-amber-200'
          }`}>
            <div className="flex items-center gap-3 mb-2">
              <span className={`h-3 w-3 rounded-full ${result.color === 'green' ? 'bg-emerald-500' : result.color === 'amber' ? 'bg-orange-400' : 'bg-amber-400'}`} />
              <h2 className="text-lg font-bold text-[#161412]">{result.overall_status}</h2>
            </div>
            <p className="text-sm text-[#161412]/75">{result.reasoning}</p>
            <div className="mt-3 flex items-center gap-4 text-xs text-[#161412]/55">
              <span>Confidence: <strong className="text-[#176B45]">{result.confidence}</strong></span>
            </div>
          </div>

          {/* Key Findings */}
          {result.key_findings?.length > 0 && (
            <div className="rounded-xl border border-[#161412]/10 bg-white p-5 shadow-sm">
              <h3 className="text-xs font-bold uppercase tracking-wider text-[#176B45] mb-4">Key Findings</h3>
              <div className="space-y-2">
                {result.key_findings.slice(0, 5).map((finding, i) => (
                  <div key={`${finding}-${i}`} className="flex gap-2 rounded-lg bg-[#f4f6f3] p-3">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#176B45]" />
                    <p className="text-sm text-[#161412]/75">{finding}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Information Gaps */}
          {result.information_gaps?.length > 0 && (
            <div className="rounded-xl border border-orange-200 bg-orange-50/60 p-5">
              <div className="flex items-start gap-3">
                <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-orange-700" />
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-orange-800 mb-2">Information needed to finalize ABS pathway</h3>
                  <ul className="space-y-1 text-sm text-orange-900/80">
                    {result.information_gaps.map((gap) => (
                      <li key={gap} className="flex gap-2">
                        <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-orange-500" />{gap}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Obligation Cards */}
          {obligations.length > 0 && (
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-[#176B45] mb-4">Obligation Navigator</h3>
              <div className="grid gap-4 md:grid-cols-2">
                {obligations.map((item) => <ObligationMini key={item.area} item={item} />)}
              </div>
            </div>
          )}

          {/* Evidence */}
          {result.evidence?.length > 0 && (
            <div className="rounded-xl border border-[#161412]/10 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <BookOpen className="h-4 w-4 text-[#176B45]" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-[#176B45]">Evidence / Sources</h3>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {result.evidence.map((ev) => (
                  <div key={ev.source_chunk_id} className="rounded-lg border border-[#161412]/10 bg-[#fbfcfa] p-3 text-xs">
                    <p className="font-semibold text-[#176B45]">{ev.document || ev.source}</p>
                    {ev.section && <p className="text-[#161412]/50">Section {ev.section}</p>}
                    <p className="mt-1 line-clamp-3 text-[#161412]/70">{ev.excerpt}</p>
                    {ev.relevance && <p className="mt-1 text-[#161412]/50"><span className="font-semibold">Relevance:</span> {ev.relevance}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Disclaimer */}
          <p className="text-xs text-[#161412]/45 text-center">{result.disclaimer}</p>
          <div className="flex justify-center">
            <a href="/abs" className="inline-flex items-center gap-2 rounded-lg border border-[#cfdad1] bg-white px-5 py-2.5 text-xs font-semibold text-[#161412]/70 hover:border-[#176B45] hover:text-[#176B45] transition">
              Full ABS screening with context <ArrowRight className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
