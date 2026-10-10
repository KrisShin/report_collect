import { Suspense, type ReactNode } from 'react'

export default function LazyPage({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="page-loading">
          <div className="page-loading-spinner" />
        </div>
      }
    >
      {children}
    </Suspense>
  )
}
