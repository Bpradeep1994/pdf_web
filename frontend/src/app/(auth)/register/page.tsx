"use client";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import toast from "react-hot-toast";
import { FileText, Loader2 } from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import { cn } from "@/lib/utils";

const schema = z.object({
  full_name: z.string().min(1, "Name is required"),
  email:     z.string().email("Invalid email"),
  password:  z.string().min(8, "At least 8 characters"),
  confirm:   z.string(),
}).refine((d) => d.password === d.confirm, { message: "Passwords don't match", path: ["confirm"] });

type FormData = z.infer<typeof schema>;

export default function RegisterPage() {
  const router = useRouter();
  const { register: signup, isLoading } = useAuthStore();

  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: FormData) => {
    try {
      await signup(data.email, data.password, data.full_name);
      toast.success("Account created! Welcome aboard.");
      router.push("/dashboard");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? "Registration failed");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-8 bg-slate-50">
      <div className="w-full max-w-md animate-fade-in">
        <div className="flex items-center gap-2 mb-8">
          <FileText className="w-6 h-6 text-brand-600" />
          <span className="text-xl font-bold">PDF Editor</span>
        </div>

        <div className="card p-8">
          <h1 className="text-2xl font-bold text-slate-900 mb-1">Create your account</h1>
          <p className="text-slate-500 mb-6">Start editing PDFs with AI for free</p>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="label">Full name</label>
              <input {...register("full_name")} placeholder="Jane Smith" className={cn("input", errors.full_name && "border-red-400")} />
              {errors.full_name && <p className="text-red-500 text-xs mt-1">{errors.full_name.message}</p>}
            </div>
            <div>
              <label className="label">Email</label>
              <input {...register("email")} type="email" placeholder="you@example.com" className={cn("input", errors.email && "border-red-400")} />
              {errors.email && <p className="text-red-500 text-xs mt-1">{errors.email.message}</p>}
            </div>
            <div>
              <label className="label">Password</label>
              <input {...register("password")} type="password" placeholder="••••••••" className={cn("input", errors.password && "border-red-400")} />
              {errors.password && <p className="text-red-500 text-xs mt-1">{errors.password.message}</p>}
            </div>
            <div>
              <label className="label">Confirm password</label>
              <input {...register("confirm")} type="password" placeholder="••••••••" className={cn("input", errors.confirm && "border-red-400")} />
              {errors.confirm && <p className="text-red-500 text-xs mt-1">{errors.confirm.message}</p>}
            </div>

            <button type="submit" disabled={isLoading} className="btn-primary w-full justify-center py-2.5">
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Create account"}
            </button>
          </form>

          <p className="text-center text-xs text-slate-500 mt-4">
            By signing up you agree to our{" "}
            <Link href="/terms" className="underline">Terms</Link> and{" "}
            <Link href="/privacy" className="underline">Privacy Policy</Link>.
          </p>
        </div>

        <p className="text-center text-sm text-slate-500 mt-4">
          Already have an account?{" "}
          <Link href="/login" className="text-brand-600 font-medium hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
