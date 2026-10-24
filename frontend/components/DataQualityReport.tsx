import StatusBadge from "@/components/StatusBadge";
import type { Dataset, QualityWarning } from "@/lib/types";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function WarningItem({ warning }: { warning: QualityWarning }) {
  const isWarning = warning.severity === "warning";
  return (
    <li className="flex gap-2 rounded-md border border-border bg-surface p-3">
      <span aria-hidden="true" className={isWarning ? "text-warning" : "text-accent"}>
        {isWarning ? "⚠" : "ℹ"}
      </span>
      <div>
        <p>
          <span className="sr-only">{isWarning ? "Warning: " : "Note: "}</span>
          {warning.message}
        </p>
        {warning.columns.length > 0 && (
          <p className="text-sm text-muted">Columns: {warning.columns.join(", ")}</p>
        )}
      </div>
    </li>
  );
}

export default function DataQualityReport({ dataset }: { dataset: Dataset }) {
  const report = dataset.validation;

  return (
    <section aria-labelledby="report-title" className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 id="report-title" className="text-2xl font-semibold break-all">
          {dataset.original_filename}
        </h1>
        <StatusBadge status={dataset.status} />
      </header>

      {!report && (
        <p className="text-muted">This file has been uploaded but not validated yet.</p>
      )}

      {report?.status === "REJECTED" && (
        <div role="alert" className="rounded-md border border-danger p-4">
          <p className="font-medium text-danger">This file was rejected.</p>
          <p>{report.message}</p>
        </div>
      )}

      {report?.status === "READY" && (
        <>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            {[
              ["Rows", report.row_count?.toLocaleString() ?? "–"],
              ["Columns", report.column_count?.toLocaleString() ?? "–"],
              ["File size", formatBytes(dataset.size_bytes)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-md border border-border bg-surface p-3">
                <dt className="text-sm text-muted">{label}</dt>
                <dd className="text-xl font-semibold tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>

          <div>
            <h2 className="mb-2 text-lg font-semibold">Data quality</h2>
            {report.warnings.length === 0 ? (
              <p className="text-muted">No data-quality warnings were found.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {report.warnings.map((warning) => (
                  <WarningItem key={warning.code} warning={warning} />
                ))}
              </ul>
            )}
          </div>

          <div>
            <h2 className="mb-2 text-lg font-semibold">Schema</h2>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-sm">
                <caption className="sr-only">Columns, types and missing values</caption>
                <thead className="bg-surface">
                  <tr>
                    <th scope="col" className="p-2">Column</th>
                    <th scope="col" className="p-2">Type</th>
                    <th scope="col" className="p-2 text-right">Missing</th>
                    <th scope="col" className="p-2 text-right">Distinct values</th>
                  </tr>
                </thead>
                <tbody>
                  {report.columns.map((column) => (
                    <tr key={column.name} className="border-t border-border">
                      <th scope="row" className="p-2 font-medium break-all">{column.name}</th>
                      <td className="p-2">{column.kind}</td>
                      <td className="p-2 text-right tabular-nums">
                        {column.missing_count.toLocaleString()} ({column.missing_percent}%)
                      </td>
                      <td className="p-2 text-right tabular-nums">
                        {column.unique_count.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
