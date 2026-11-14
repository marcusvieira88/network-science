import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { DeparturePeriodRow, DepartureTestRow } from "@/lib/data";
import {
  type Departure,
  HIGHER_RATE,
  NOT_PUBLISHED,
  countText,
  departureStatement,
  evidenceSentence,
  pText,
  powerSentence,
  rollingSentence,
  splitSentence,
  variantSentence,
} from "@/lib/departures";
import { formatFloat } from "@/lib/format";
import { TIMING_LABELS, TIMING_MEANINGS } from "@/lib/hypotheses";

/** The candidate finding as stated in docs/hypotheses-exploratory.md (O1, "Decision rule"). */
const CLAIM = `Prediction: ${HIGHER_RATE} in the same weeks a year earlier and than in any comparable earlier window.`;

function yesNo(value: boolean | null): string {
  return value === null ? NOT_PUBLISHED : value ? "yes" : "no";
}

function PeriodRow({ row, k }: { row: DeparturePeriodRow; k: number }) {
  return (
    <TableRow>
      <TableCell>{row.period}</TableCell>
      <TableCell className="whitespace-nowrap font-mono tabular-nums">{row.period_start}</TableCell>
      <TableCell className="whitespace-nowrap font-mono tabular-nums">{row.period_end}</TableCell>
      <TableCell className="text-right tabular-nums">{countText(row.at_risk, k)}</TableCell>
      <TableCell className="text-right tabular-nums">{countText(row.departures, k)}</TableCell>
      <TableCell className="text-right tabular-nums">{countText(row.record_ends, k)}</TableCell>
      <TableCell className="text-right tabular-nums">{row.hazard === null ? NOT_PUBLISHED : formatFloat(row.hazard)}</TableCell>
    </TableRow>
  );
}

function VariantRow({ row, departure }: { row: DepartureTestRow; departure: Departure }) {
  return (
    <TableRow>
      <TableCell>{row.variant}</TableCell>
      <TableCell>{yesNo(row.in_rule)}</TableCell>
      <TableCell>{yesNo(row.crisis_above_reference)}</TableCell>
      <TableCell className="whitespace-nowrap">{pText(row.p, row.p_band, departure.settings)}</TableCell>
      <TableCell className="whitespace-nowrap">{pText(row.placebo_p, row.placebo_p_band, departure.settings)}</TableCell>
      <TableCell>{yesNo(row.above_rolling)}</TableCell>
    </TableRow>
  );
}

/** H26 in full: statement, windows and counts, the test, the robustness variants and the power. */
export function DepartureDetails({ departure }: { departure: Departure }) {
  const { k } = departure.settings;
  const power = powerSentence(departure);
  return (
    <div className="space-y-4 text-sm" data-testid="departure-details">
      <p className="text-muted-foreground">Stated {TIMING_LABELS.postHoc}: {TIMING_MEANINGS.postHoc}.</p>
      <div className="space-y-1">
        <h4 className="font-medium">Statement</h4>
        <p>{CLAIM}</p>
        <p className="text-muted-foreground">{departureStatement(departure.settings)}</p>
      </div>
      <div className="space-y-1">
        <h4 className="font-medium">Windows and counts</h4>
        <p className="text-muted-foreground">
          Custodians at risk at each window&apos;s start, how many departed and how many records ended. Counts below {k}, or
          that would reveal fewer than {k} by subtraction, read &ldquo;fewer than {k}&rdquo;.
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Window</TableHead>
              <TableHead>From</TableHead>
              <TableHead>To</TableHead>
              <TableHead className="text-right">At risk</TableHead>
              <TableHead className="text-right">Departures</TableHead>
              <TableHead className="text-right">Record ends</TableHead>
              <TableHead className="text-right">Share departed</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {departure.periods.map((row) => (
              <PeriodRow key={row.period} row={row} k={k} />
            ))}
          </TableBody>
        </Table>
        <p className="text-muted-foreground">{splitSentence(departure)}</p>
      </div>
      <div className="space-y-1">
        <h4 className="font-medium">Test</h4>
        <p>{evidenceSentence(departure)}</p>
        <p>{rollingSentence(departure)}</p>
      </div>
      <div className="space-y-1">
        <h4 className="font-medium">Robustness variants</h4>
        <p>{variantSentence(departure)}</p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Variant</TableHead>
              <TableHead>In the rule</TableHead>
              <TableHead>Crisis share above reference</TableHead>
              <TableHead>p (crisis against reference)</TableHead>
              <TableHead>Placebo p</TableHead>
              <TableHead>Above every earlier window</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {departure.tests.map((row) => (
              <VariantRow key={row.variant} row={row} departure={departure} />
            ))}
          </TableBody>
        </Table>
      </div>
      {power !== null && (
        <div className="space-y-1">
          <h4 className="font-medium">Power</h4>
          <p>{power}</p>
        </div>
      )}
    </div>
  );
}
