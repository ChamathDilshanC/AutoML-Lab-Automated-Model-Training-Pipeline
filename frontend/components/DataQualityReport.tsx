import { LuColumns3, LuHardDrive, LuHash, LuInfo, LuRows3, LuTags, LuTriangleAlert } from "react-icons/lu";
import Alert from "@/components/ui/Alert";
import StatCard from "@/components/ui/StatCard";
import { AnimatedList } from "@/components/unlumen-ui/animated-list";
import type { ColumnSummary, Dataset, QualityWarning } from "@/lib/types";
import { cardClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function WarningItem({ warning }: { warning: QualityWarning }) {
  const isWarning = warning.severity === "warning";
  const Icon = isWarning ? LuTriangleAlert : LuInfo;
  return (
    <div
      className={cn(
        "flex gap-3 rounded-2xl border p-4 text-sm",
        isWarning ? "border-warning/25 bg-warning/[0.04]" : "border-accent/20 bg-accent/[0.03]",
      )}
    >
      <Icon
        aria-hidden="true"
        className={cn("mt-0.5 size-4 shrink-0", isWarning ? "text-warning" : "text-accent")}
      />
      <div className="flex min-w-0 flex-col gap-2">
        <p>
          <span className="sr-only">{isWarning ? "Warning: " : "Note: "}</span>
          {warning.message}
        </p>
        {warning.columns.length > 0 && (
          <p className="flex flex-wrap gap-1.5">
            <span className="sr-only">Columns: </span>
            {warning.columns.map((column) => (
              <span
                key={column}
                className="rounded-md border border-border/70 bg-bg px-1.5 py-0.5 font-mono text-xs break-all text-muted"
              >
                {column}
              </span>
            ))}
          </p>
        )}
      </div>
    </div>
  );
}

function KindChip({ kind }: { kind: ColumnSummary["kind"] }) {
  const Icon = kind === "numeric" ? LuHash : LuTags;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-surface px-2.5 py-0.5 text-xs font-medium text-text/80">
      <Icon aria-hidden="true" className="size-3" />
      {kind}
    </span>
  );
}

/** The validation outcome: figures, schema and data-quality warnings. */
export default function DataQualityReport({ dataset }: { dataset: Dataset }) {
  const report = dataset.validation;

  if (!report) {
    return (
      <Alert tone="info" title="Not validated yet">
        This file has not been validated yet. If the upload never finished, delete this dataset and
        upload the file again.
      </Alert>
    );
  }

  if (report.status === "REJECTED") {
    return (
      <Alert role="alert" title="This file was rejected.">
        {report.message}
      </Alert>
    );
  }

  if (report.status !== "READY") return null;

  return (
    <div className="flex flex-col gap-8">
      <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Rows" value={report.row_count?.toLocaleString() ?? "–"} icon={LuRows3} />
        <StatCard
          label="Columns"
          value={report.column_count?.toLocaleString() ?? "–"}
          icon={LuColumns3}
        />
        <StatCard label="File size" value={formatBytes(dataset.size_bytes)} icon={LuHardDrive} />
        <StatCard
          label="Warnings"
          value={report.warnings.filter((w) => w.severity === "warning").length}
          icon={LuTriangleAlert}
          hint={`${report.warnings.length} note${report.warnings.length === 1 ? "" : "s"} in total`}
        />
      </dl>

      <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-12">
        <section
          aria-labelledby="schema-title"
          className={cn(cardClass, "overflow-hidden rounded-2xl lg:col-span-8")}
        >
          <div className="flex items-center justify-between gap-3 border-b border-border/60 px-6 py-4">
            <h2 id="schema-title" className="font-semibold tracking-tight">
              Schema
            </h2>
            <span className="text-sm text-muted">{report.columns.length} columns</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <caption className="sr-only">Columns, types and missing values</caption>
              <thead className="bg-surface/60 text-xs tracking-wide text-muted uppercase">
                <tr>
                  <th scope="col" className="px-6 py-3 font-medium">Column</th>
                  <th scope="col" className="px-6 py-3 font-medium">Type</th>
                  <th scope="col" className="px-6 py-3 text-right font-medium">Missing</th>
                  <th scope="col" className="px-6 py-3 text-right font-medium">Distinct values</th>
                </tr>
              </thead>
              <tbody>
                {report.columns.map((column) => (
                  <tr
                    key={column.name}
                    className="border-t border-border/50 transition-colors hover:bg-surface/40"
                  >
                    <th scope="row" className="px-6 py-3 font-medium break-all">
                      {column.name}
                    </th>
                    <td className="px-6 py-3">
                      <KindChip kind={column.kind} />
                    </td>
                    <td className="px-6 py-3">
                      <div className="flex items-center justify-end gap-3 tabular-nums">
                        <span>
                          {column.missing_count.toLocaleString()}{" "}
                          <span className="text-muted">({column.missing_percent}%)</span>
                        </span>
                        <span aria-hidden="true" className="hidden h-1.5 w-16 rounded-full bg-surface sm:block">
                          <span
                            className={cn(
                              "block h-full rounded-full",
                              column.missing_percent > 0 ? "bg-warning" : "bg-success",
                            )}
                            style={{ width: `${Math.max(column.missing_percent, 4)}%` }}
                          />
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-3 text-right tabular-nums">
                      {column.unique_count.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section
          aria-labelledby="quality-title"
          className={cn(cardClass, "flex flex-col gap-4 rounded-2xl p-6 lg:col-span-4")}
        >
          <h2 id="quality-title" className="font-semibold tracking-tight">
            Data quality
          </h2>
          {report.warnings.length === 0 ? (
            <Alert tone="success">No data-quality warnings were found.</Alert>
          ) : (
            <AnimatedList
              items={report.warnings.map((warning) => ({ id: warning.code, warning }))}
              maxVisible={report.warnings.length}
              gap={10}
              animation="slide"
              renderItem={({ warning }) => <WarningItem warning={warning} />}
            />
          )}
        </section>
      </div>
    </div>
  );
}
