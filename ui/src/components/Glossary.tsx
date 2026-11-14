import { GLOSSARY } from "@/lib/glossary";

/** The analysis terms in plain words, folded by default so it never pushes the results down. */
export function Glossary() {
  return (
    <details className="rounded-lg border bg-card px-4 py-3 text-sm">
      <summary className="cursor-pointer font-medium">What the terms mean</summary>
      <dl className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2">
        {GLOSSARY.map(({ term, meaning }) => (
          <div key={term}>
            <dt className="font-medium">{term}</dt>
            <dd className="text-muted-foreground">{meaning}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
