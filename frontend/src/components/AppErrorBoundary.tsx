import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { hasError: boolean };

/** Prevents an unexpected render error from blanking the entire workspace. */
export default class AppErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("OpsPilot UI render error", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="grid min-h-screen place-items-center bg-slate-50 px-5 py-12">
          <section role="alert" className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-rose-50 text-xl text-rose-600">!</div>
            <h1 className="mt-5 text-xl font-semibold tracking-tight text-slate-900">Something went wrong</h1>
            <p className="mt-2 text-sm leading-6 text-slate-500">OpsPilot couldn't render this view. Reload the workspace to try again.</p>
            <button type="button" onClick={() => window.location.reload()} className="mt-6 inline-flex min-h-10 items-center justify-center rounded-xl bg-[#10243a] px-5 text-sm font-semibold text-white transition hover:bg-[#1b3854] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2">Reload workspace</button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}
