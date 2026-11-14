import { GLOSSARY } from "@/lib/glossary";

/** Every term and its plain meaning. */
export function GlossaryList() {
  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
      {GLOSSARY.map(({ term, meaning }) => (
        <div key={term}>
          <dt className="font-medium">{term}</dt>
          <dd className="text-muted-foreground">{meaning}</dd>
        </div>
      ))}
    </dl>
  );
}

/** The analysis terms in plain words, folded by default so it never pushes the results down. */
export function Glossary() {
  return (
    <details className="rounded-lg border bg-card px-4 py-3 text-sm">
      <summary className="cursor-pointer font-medium">What the terms mean</summary>
      <div className="mt-3">
        <GlossaryList />
      </div>
    </details>
  );
}
