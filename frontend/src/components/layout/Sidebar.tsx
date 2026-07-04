"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  FileText, LayoutDashboard, CreditCard, FolderKanban, Wrench,
  Settings, Shield, LogOut, ChevronLeft, ChevronRight,
} from "lucide-react";
import { useState } from "react";
import { useAuthStore, isStaff } from "@/lib/auth";
import { cn } from "@/lib/utils";
import toast from "react-hot-toast";

const navItems = [
  { href: "/dashboard",  icon: LayoutDashboard, label: "Dashboard" },
  { href: "/tools",      icon: Wrench,          label: "Tools"     },
  { href: "/projects",   icon: FolderKanban,    label: "Projects"  },
  { href: "/billing",    icon: CreditCard,      label: "Billing"   },
  { href: "/settings",   icon: Settings,        label: "Settings"  },
];

const adminItems = [
  { href: "/admin", icon: Shield, label: "Admin" },
];

export default function Sidebar() {
  const pathname           = usePathname();
  const router             = useRouter();
  const { user, logout }   = useAuthStore();
  const [collapsed, setCollapsed] = useState(false);

  const handleLogout = async () => {
    await logout();
    router.push("/login");
    toast.success("Signed out");
  };

  const NavItem = ({ href, icon: Icon, label }: { href: string; icon: any; label: string }) => (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
        pathname.startsWith(href)
          ? "bg-brand-50 text-brand-700"
          : "text-slate-600 hover:bg-slate-100",
        collapsed && "justify-center px-2"
      )}
      title={collapsed ? label : undefined}
    >
      <Icon className="w-5 h-5 flex-shrink-0" />
      {!collapsed && <span>{label}</span>}
    </Link>
  );

  return (
    <aside className={cn(
      "flex flex-col h-screen bg-white border-r border-slate-200 transition-all duration-200",
      collapsed ? "w-16" : "w-60"
    )}>
      {/* Logo */}
      <div className={cn("flex items-center gap-3 p-4 border-b border-slate-100", collapsed && "justify-center")}>
        <FileText className="w-7 h-7 text-brand-600 flex-shrink-0" />
        {!collapsed && <span className="font-bold text-slate-900">PDF Editor</span>}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto p-3 space-y-1">
        {navItems.map((item) => <NavItem key={item.href} {...item} />)}

        {isStaff(user) && (
          <>
            <div className={cn("pt-3 pb-1 px-3", collapsed && "px-1")}>
              {!collapsed && <p className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">Admin</p>}
            </div>
            {adminItems.map((item) => <NavItem key={item.href} {...item} />)}
          </>
        )}
      </nav>

      {/* User + Collapse */}
      <div className="p-3 border-t border-slate-100 space-y-2">
        {!collapsed && user && (
          <div className="flex items-center gap-2 px-3 py-2">
            <div className="w-7 h-7 rounded-full bg-brand-100 flex items-center justify-center text-brand-700 text-xs font-bold flex-shrink-0">
              {user.full_name?.[0]?.toUpperCase() ?? user.email[0].toUpperCase()}
            </div>
            <div className="overflow-hidden">
              <p className="text-sm font-medium text-slate-900 truncate">{user.full_name ?? user.email}</p>
              <p className="text-xs text-slate-500 capitalize">{user.role}</p>
            </div>
          </div>
        )}
        <button onClick={handleLogout}
          className={cn("flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm text-slate-500 hover:bg-red-50 hover:text-red-600 transition-colors", collapsed && "justify-center px-2")}>
          <LogOut className="w-5 h-5 flex-shrink-0" />
          {!collapsed && "Sign out"}
        </button>
        <button onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex items-center justify-center w-full py-1 text-slate-500 hover:text-slate-600">
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>
    </aside>
  );
}
