"""Draws docs/architecture.png, the AWS architecture of infrastructure/terraform/.

Run from anywhere:  python docs/architecture/generate_architecture.py
Needs only matplotlib. When the Terraform changes, change the boxes below and run it again.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

OUT = Path(__file__).resolve().parents[1] / "architecture.png"

W, H = 20.0, 17.0
INK = "#1F2933"
MUTED = "#52606D"
LINE = "#3E4C59"

# AWS category colours.
COMPUTE = "#ED7100"
STORAGE = "#7AA116"
DATABASE = "#3B48CC"
INTEGRATION = "#E7157B"
SECURITY = "#DD344C"
NETWORK = "#8C4FFF"
EXTERNAL = "#232F3E"

fig, ax = plt.subplots(figsize=(W, H))
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")

Y0 = 2.6  # everything above the legend is drawn in a frame that starts at y = 0 and shifted up


def box(x, y, w, h, *, face="white", edge=LINE, lw=1.4, dash=None, radius=0.08, z=1):
    ax.add_patch(
        FancyBboxPatch(
            (x, y + Y0),
            w,
            h,
            boxstyle=f"round,pad=0,rounding_size={radius}",
            facecolor=face,
            edgecolor=edge,
            linewidth=lw,
            linestyle=dash or "-",
            zorder=z,
        )
    )


def text(x, y, s, *, size=10, color=INK, weight="normal", ha="left", va="center", z=5, style="normal"):
    ax.text(x, y + Y0, s, fontsize=size, color=color, fontweight=weight, ha=ha, va=va, zorder=z, fontstyle=style)


def service(x, y, w, h, color, name, lines):
    """A service card: coloured header with the AWS service name, white body with details."""
    box(x, y, w, h, face="white", edge=color, lw=1.8, z=2)
    ax.add_patch(
        FancyBboxPatch(
            (x, y + h - 0.42 + Y0),
            w,
            0.42,
            boxstyle="round,pad=0,rounding_size=0.08",
            facecolor=color,
            edgecolor=color,
            linewidth=1.8,
            zorder=3,
        )
    )
    text(x + 0.14, y + h - 0.21, name, size=12.5, color="white", weight="bold", z=6)
    step = 0.27
    for i, line in enumerate(lines):
        text(x + 0.14, y + h - 0.68 - i * step, line, size=10, color=INK, z=6)


def arrow(points, *, color=LINE, dash=None, badge=None, badge_at=0, lw=1.9):
    xs = [p[0] for p in points]
    ys = [p[1] + Y0 for p in points]
    ax.plot(xs[:-1] + [xs[-1]], ys[:-1] + [ys[-1]], color=color, linewidth=lw, linestyle=dash or "-", zorder=4)
    ax.annotate(
        "",
        xy=(xs[-1], ys[-1]),
        xytext=(xs[-2], ys[-2]),
        arrowprops=dict(arrowstyle="-|>", color=color, linewidth=lw, mutation_scale=18),
        zorder=4,
    )
    if badge is not None:
        (ax1, ay1), (ax2, ay2) = points[badge_at], points[badge_at + 1]
        f = 0.5 if abs(ax2 - ax1) + abs(ay2 - ay1) > 1.5 else 0.3
        mx, my = ax1 + (ax2 - ax1) * f, ay1 + (ay2 - ay1) * f
        number(mx, my, badge)


def number(x, y, n):
    ax.add_patch(plt.Circle((x, y + Y0), 0.19, facecolor=EXTERNAL, edgecolor="white", linewidth=1.5, zorder=8))
    text(x, y, str(n), size=10.5, color="white", weight="bold", ha="center", z=9)


# ---- title ----------------------------------------------------------------------------------
ax.text(0.4, H - 0.45, "AutoML Lab — AWS architecture", fontsize=24, fontweight="bold", color=INK, va="center")
ax.text(
    0.4,
    H - 0.95,
    "Region us-east-1 · as defined in infrastructure/terraform/ · base layer applied; API, worker and frontend not yet",
    fontsize=12.5,
    color=MUTED,
    va="center",
)

# ---- outside AWS ----------------------------------------------------------------------------
service(0.3, 10.9, 2.9, 1.4, EXTERNAL, "User browser", ["Signs in, uploads a CSV,", "reviews results, predicts"])
service(0.3, 6.3, 2.9, 1.6, EXTERNAL, "Amplify Hosting", ["Next.js frontend from GitHub", "(or Vercel); no AWS keys"])
service(0.3, 0.8, 2.9, 1.9, EXTERNAL, "GitHub Actions", ["deploy.yml, environment", "“production”; short-lived", "OIDC token, no AWS keys"])

# ---- AWS cloud ------------------------------------------------------------------------------
box(3.6, 0.3, 16.1, 12.85, face="#FBFBFD", edge="#232F3E", lw=2.2, radius=0.12, z=0)
text(3.8, 12.93, "AWS Cloud · us-east-1", size=14, weight="bold", color="#232F3E")

# Regional services strip (outside the VPC).
box(3.85, 10.75, 15.6, 1.97, face="#F3F5F7", edge="#9AA5B1", lw=1.2, dash="--", z=0)
text(4.0, 12.52, "Regional services (outside the VPC)", size=10.5, color=MUTED, style="italic")
service(4.1, 10.85, 3.5, 1.5, STORAGE, "Amazon S3", ["Datasets and models, AES-256", "Public access blocked, TLS only", "CORS for presigned uploads"])
service(7.85, 10.85, 3.5, 1.5, INTEGRATION, "Amazon SQS", ["automl-lab-experiments-queue", "Dead-letter queue after 3 tries", "SSE on, TLS-only policy"])
service(11.6, 10.85, 3.5, 1.5, SECURITY, "SSM Parameter Store", ["/automl-lab/db-password", "/automl-lab/jwt-secret", "Read by the worker at start"])
service(15.35, 10.85, 3.9, 1.5, COMPUTE, "Amazon ECR", ["automl-lab-backend (API + worker)", "Scan on push, keeps last 20", "AES-256"])

# Lambda (public Function URL; the function's network interfaces sit in the private subnets).
service(4.1, 5.4, 3.2, 2.6, COMPUTE, "AWS Lambda · API", ["automl-lab-api (image)", "FastAPI via Web Adapter", "Public HTTPS Function URL", "Runs in the private subnets", "Secrets as encrypted env"])

# IAM / OIDC.
service(4.1, 0.6, 3.2, 2.4, SECURITY, "IAM · GitHub OIDC", ["OIDC provider and role", "automl-lab-github-deploy", "Only this repo and the", "“production” environment", "ECR push, Lambda and", "ECS roll-out"])

# VPC.
box(8.0, 0.55, 11.5, 9.0, face="#F7F4FF", edge=NETWORK, lw=2.4, radius=0.12, z=0)
text(9.0, 9.2, "VPC · automl-lab-vpc · 10.20.0.0/16", size=12, weight="bold", color=NETWORK)

# Public subnets.
box(8.3, 5.4, 10.9, 3.1, face="#EEF6EC", edge=STORAGE, lw=1.4, dash="--", z=0)
text(9.1, 8.25, "Public subnets · 10.20.0.0/24 · 10.20.1.0/24", size=10.5, color="#3F6212", weight="bold")
service(8.55, 5.6, 3.1, 2.2, NETWORK, "S3 gateway endpoint", ["On the public and", "private route tables;", "S3 traffic stays inside", "AWS"])
service(12.0, 5.6, 4.5, 2.2, COMPUTE, "ECS Fargate · worker", ["Cluster automl-lab-cluster", "Service automl-lab-worker (1 task)", "Runs python -m worker.main", "Public IP, no NAT gateway", "Logs go to CloudWatch Logs"])

# Internet gateway sits on the VPC border.
box(14.7, 9.25, 1.9, 0.6, face=NETWORK, edge=NETWORK, z=6)
text(15.65, 9.55, "Internet gateway", size=10.5, color="white", weight="bold", ha="center", z=7)

# Private subnets.
box(8.3, 0.8, 10.9, 4.3, face="#EEF3FB", edge=DATABASE, lw=1.4, dash="--", z=0)
text(8.45, 4.85, "Private subnets · 10.20.10.0/24 · 10.20.11.0/24", size=10.5, color="#2B3A9E", weight="bold")
text(8.45, 4.5, "No route to the internet", size=9.5, color="#2B3A9E")
service(8.55, 2.0, 2.7, 2.1, COMPUTE, "Lambda ENIs", ["The API's network", "interfaces; security group:", "no inbound traffic"])
service(11.9, 2.0, 3.4, 2.1, DATABASE, "Amazon RDS", ["PostgreSQL, db.t4g.micro", "20 GiB gp3, encrypted, TLS", "Reachable from the API and", "the worker only"])
service(15.9, 2.0, 3.1, 2.1, NETWORK, "SQS endpoint", ["Interface endpoint,", "private DNS, subnet a;", "HTTPS from the VPC only"])

# ---- arrows ---------------------------------------------------------------------------------
# 1 browser -> Amplify
arrow([(1.75, 10.9), (1.75, 7.9)], badge=1)
# 2 Amplify -> Lambda
arrow([(3.2, 7.0), (4.1, 7.0)], badge=2, badge_at=0)
# 3 browser -> S3 (presigned PUT)
arrow([(3.2, 11.6), (4.1, 11.6)], badge=3)
# 4 Lambda -> its ENIs -> RDS
arrow([(6.5, 5.4), (6.5, 3.3), (8.55, 3.3)], badge=4, badge_at=0)
arrow([(11.25, 3.3), (11.9, 3.3)])
# 5 ENIs -> SQS endpoint (under RDS)
arrow([(9.9, 2.0), (9.9, 1.4), (17.45, 1.4), (17.45, 2.0)], badge=5, badge_at=1)
# 6 worker -> RDS, S3 endpoint, SQS endpoint, IGW
arrow([(13.6, 5.6), (13.6, 4.1)])
number(13.6, 5.25, 6)
arrow([(12.0, 6.7), (11.65, 6.7)])
arrow([(16.2, 5.6), (16.2, 4.1)])
arrow([(15.65, 7.8), (15.65, 9.25)])
# SQS endpoint -> SQS (up the right side, then left above the VPC)
arrow([(18.0, 4.1), (18.0, 10.35), (9.35, 10.35), (9.35, 10.85)])
# S3 endpoint -> S3
arrow([(8.8, 7.8), (8.8, 10.05), (5.7, 10.05), (5.7, 10.85)])
# IGW -> regional services
arrow([(15.65, 9.85), (15.65, 10.85)])
# 7 GitHub -> IAM role -> Lambda
arrow([(3.2, 1.8), (4.1, 1.8)], badge=7)
arrow([(4.9, 3.0), (4.9, 5.4)], dash=(0, (5, 3)))

# ---- legend ---------------------------------------------------------------------------------
ax.add_patch(Rectangle((0.3, 0.2), 19.4, 2.1, facecolor="white", edgecolor="#9AA5B1", linewidth=1.2, zorder=0))
legend = [
    (1, "The browser loads the Next.js UI from Amplify Hosting (or Vercel)."),
    (2, "The UI calls the API's Lambda Function URL over HTTPS with a bearer token."),
    (3, "The browser uploads a CSV straight to S3 with a presigned PUT URL."),
    (4, "The API reaches RDS through its network interfaces (PostgreSQL over TLS)."),
    (5, "The API puts experiment jobs on SQS through the interface endpoint."),
    (6, "The worker polls SQS, reads and writes S3 via the gateway endpoint, writes RDS."),
    (7, "GitHub Actions swaps its OIDC token for the deploy role, pushes to ECR, then rolls out."),
]
for i, (n, s_) in enumerate(legend):
    col, row = divmod(i, 4)
    x = 0.6 + col * 9.9
    y_abs = 2.0 - row * 0.36
    number(x, y_abs - Y0, n)
    text(x + 0.35, y_abs - Y0, s_, size=10.5)
text(
    10.0,
    0.45 - Y0,
    "The Lambda API and the Fargate worker exist only when enable_compute = true, Amplify only when "
    "enable_frontend = true. The worker reads the SSM secrets; the API gets them as encrypted env vars.",
    size=10,
    color=MUTED,
    style="italic",
    ha="center",
)

fig.savefig(OUT, dpi=200, bbox_inches="tight", pad_inches=0.2, facecolor="white")
print(f"wrote {OUT}")
