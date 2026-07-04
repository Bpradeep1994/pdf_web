"use client";
import { useEffect, useState } from "react";
import { FolderKanban, Plus, Trash2, Loader2, Users } from "lucide-react";
import toast from "react-hot-toast";
import { projectsApi } from "@/lib/api";
import { formatRelative } from "@/lib/utils";

interface Project { id: string; name: string; description?: string; member_count?: number; document_count?: number; created_at: string; }

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");

  const load = async () => {
    try { setProjects((await projectsApi.list()).data); } catch { setProjects([]); }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!name.trim()) return;
    try {
      await projectsApi.create({ name: name.trim(), description: desc.trim() || undefined });
      toast.success("Project created");
      setName(""); setDesc(""); setCreating(false); load();
    } catch { toast.error("Failed to create project"); }
  };
  const remove = async (id: string) => {
    if (!confirm("Delete this project?")) return;
    try { await projectsApi.remove(id); toast.success("Project deleted"); load(); }
    catch { toast.error("Failed to delete"); }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <FolderKanban className="w-6 h-6 text-brand-600" /> Projects
        </h1>
        <button onClick={() => setCreating((c) => !c)} className="btn-primary gap-1">
          <Plus className="w-4 h-4" /> New project
        </button>
      </div>

      {creating && (
        <div className="card p-5 mb-6 space-y-3">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Project name" className="input" />
          <textarea value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Description (optional)" className="input" rows={2} />
          <div className="flex gap-2">
            <button onClick={create} className="btn-primary">Create</button>
            <button onClick={() => setCreating(false)} className="btn-secondary">Cancel</button>
          </div>
        </div>
      )}

      {projects === null ? (
        <div className="py-16 flex justify-center"><Loader2 className="w-8 h-8 animate-spin text-brand-500" /></div>
      ) : projects.length === 0 ? (
        <div className="card p-12 text-center text-slate-500">
          <FolderKanban className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p>No projects yet. Create one to collaborate with your team.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {projects.map((p) => (
            <div key={p.id} className="card p-5 group">
              <div className="flex items-start justify-between">
                <h3 className="font-semibold text-slate-900">{p.name}</h3>
                <button onClick={() => remove(p.id)} className="text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100" title="Delete">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
              {p.description && <p className="text-sm text-slate-500 mt-1">{p.description}</p>}
              <div className="flex items-center gap-4 mt-4 text-xs text-slate-500">
                <span className="flex items-center gap-1"><Users className="w-3.5 h-3.5" /> {p.member_count ?? 1}</span>
                <span>{p.document_count ?? 0} docs</span>
                <span className="ml-auto">{formatRelative(p.created_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
