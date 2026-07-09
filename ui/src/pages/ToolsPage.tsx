import { useState } from 'react';
import { Wrench, BookOpen, Loader2, Code, Search, Globe, FileText, BarChart3, ExternalLink, ChevronDown, ChevronUp, Zap } from 'lucide-react';
import { useApi } from '../hooks/useApi';
import { api, type Tool, type Skill } from '../lib/api';

const toolIcons: Record<string, React.ElementType> = {
  api_caller: Globe,
  code_executor: Code,
  web_search: Search,
  file_ops: FileText,
  text_processing: FileText,
  data_analysis: BarChart3,
};

const categoryColors: Record<string, string> = {
  api: 'from-blue-500/20 to-cyan-500/20 text-blue-400',
  code: 'from-emerald-500/20 to-teal-500/20 text-emerald-400',
  search: 'from-amber-500/20 to-orange-500/20 text-amber-400',
  file: 'from-purple-500/20 to-pink-500/20 text-purple-400',
  text: 'from-cfa-500/20 to-purple-500/20 text-cfa-400',
  data: 'from-rose-500/20 to-red-500/20 text-rose-400',
};

export default function ToolsPage() {
  const tools = useApi(() => api.tools.list());
  const skills = useApi(() => api.skills.list());
  const schemas = useApi(() => api.tools.schemas());
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  const [skillDetail, setSkillDetail] = useState<Skill | null>(null);

  const toolList: Tool[] = Array.isArray(tools.data?.data) ? tools.data.data : [];
  const skillList: Skill[] = Array.isArray(skills.data?.data) ? skills.data.data : [];
  const schemaList = schemas.data?.data || [];

  const handleSkillExpand = async (name: string) => {
    if (expandedSkill === name) {
      setExpandedSkill(null);
      setSkillDetail(null);
      return;
    }
    setExpandedSkill(name);
    try {
      const res = await api.skills.get(name);
      setSkillDetail(res.data);
    } catch {
      setSkillDetail(null);
    }
  };

  return (
    <div className="space-y-8 animate-in">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Wrench className="w-6 h-6 text-cfa-400" />
          工具 & 技能
        </h1>
        <p className="text-sm text-zinc-400 mt-1">浏览可用的工具、技能和 Function Calling Schema</p>
      </div>

      <section>
        <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
          <Wrench className="w-5 h-5 text-cfa-400" />
          工具列表
          <span className="text-xs text-zinc-500 font-normal">({toolList.length})</span>
        </h2>
        {tools.loading ? (
          <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 text-cfa-400 animate-spin" /></div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {toolList.map((tool: Tool) => {
              const Icon = toolIcons[tool.name] || Wrench;
              const catColor = categoryColors[tool.category] || categoryColors.api;
              return (
                <div key={tool.name} className="glass-card rounded-2xl p-5 hover:scale-[1.01] transition-all duration-300 group">
                  <div className="flex items-start justify-between">
                    <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${catColor.split(' ')[0]} ${catColor.split(' ')[1]} flex items-center justify-center`}>
                      <Icon className={`w-5 h-5 ${catColor.split(' ')[2]}`} />
                    </div>
                    <div className={`text-xs px-2 py-0.5 rounded-full ${
                      tool.enabled ? 'bg-emerald-500/10 text-emerald-400' : 'bg-zinc-500/10 text-zinc-500'
                    }`}>
                      {tool.enabled ? '启用' : '禁用'}
                    </div>
                  </div>
                  <h3 className="text-white font-medium mt-4">{tool.name}</h3>
                  <p className="text-xs text-zinc-500 mt-1 line-clamp-2">{tool.description}</p>
                  <div className="mt-3 pt-3 border-t border-white/5 flex items-center justify-between">
                    <span className="text-[10px] text-zinc-600">{tool.category}</span>
                    <ExternalLink className="w-3 h-3 text-zinc-600 group-hover:text-cfa-400 transition-colors" />
                  </div>
                </div>
              );
            })}
            {toolList.length === 0 && (
              <div className="col-span-full glass-card rounded-2xl p-12 text-center">
                <Wrench className="w-12 h-12 text-zinc-700 mx-auto mb-4" />
                <p className="text-zinc-500">暂无可用工具</p>
              </div>
            )}
          </div>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
          <BookOpen className="w-5 h-5 text-emerald-400" />
          技能列表
          <span className="text-xs text-zinc-500 font-normal">({skillList.length})</span>
        </h2>
        {skills.loading ? (
          <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 text-cfa-400 animate-spin" /></div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {skillList.map((skill: Skill) => (
              <div key={skill.name} className="glass-card rounded-2xl p-5 hover:scale-[1.01] transition-all duration-300 group">
                <div className="flex items-start justify-between">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500/20 to-teal-500/20 flex items-center justify-center">
                    <BookOpen className="w-5 h-5 text-emerald-400" />
                  </div>
                  <button
                    onClick={() => handleSkillExpand(skill.name)}
                    className="text-zinc-500 hover:text-cfa-400 transition-colors p-1"
                  >
                    {expandedSkill === skill.name ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                </div>
                <h3 className="text-white font-medium mt-4">{skill.name}</h3>
                <p className="text-xs text-zinc-500 mt-1 line-clamp-2">{skill.description}</p>
                <div className="mt-3 flex flex-wrap gap-1">
                  {skill.triggers.map((t: string) => (
                    <span key={t} className="text-[10px] px-2 py-0.5 bg-zinc-800/50 text-zinc-300 rounded-full flex items-center gap-0.5">
                      <Zap className="w-2.5 h-2.5 text-amber-400" />
                      {t}
                    </span>
                  ))}
                </div>
                {expandedSkill === skill.name && skillDetail && skillDetail.prompt && (
                  <div className="mt-4 pt-3 border-t border-white/5">
                    <p className="text-[10px] text-zinc-600 mb-2 uppercase tracking-wider">Prompt Template</p>
                    <pre className="text-xs text-zinc-400 whitespace-pre-wrap max-h-60 overflow-y-auto bg-zinc-900/50 rounded-lg p-3">
                      {skillDetail.prompt}
                    </pre>
                  </div>
                )}
              </div>
            ))}
            {skillList.length === 0 && (
              <div className="col-span-full glass-card rounded-2xl p-8 text-center">
                <BookOpen className="w-10 h-10 text-zinc-700 mx-auto mb-4" />
                <p className="text-zinc-500">暂无可用技能</p>
              </div>
            )}
          </div>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
          <Code className="w-5 h-5 text-amber-400" />
          Function Calling Schema
          <span className="text-xs text-zinc-500 font-normal">({schemaList.length})</span>
        </h2>
        {schemas.loading ? (
          <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 text-cfa-400 animate-spin" /></div>
        ) : (
          <div className="glass-card rounded-2xl overflow-hidden">
            <pre className="p-4 text-xs text-zinc-300 overflow-x-auto max-h-80">
              {JSON.stringify(schemaList, null, 2)}
            </pre>
          </div>
        )}
      </section>
    </div>
  );
}