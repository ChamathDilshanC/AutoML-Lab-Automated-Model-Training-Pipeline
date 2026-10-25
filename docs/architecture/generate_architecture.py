"""Draws docs/architecture.png and docs/architecture.svg, the AWS architecture of
infrastructure/terraform/ as deployed.

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

W, H = 27.3, 19.6
INK = "#1F2933"
MUTED = "#52606D"
LINE = "#3E4C59"

# AWS category colours.
COMPUTE = "#ED7100"
STORAGE = "#7AA116"
DATABASE = "#3B48CC"
INTEGRATION = "#E7157B"
MANAGEMENT = "#B0084D"
SECURITY = "#DD344C"
NETWORK = "#8C4FFF"
EXTERNAL = "#232F3E"
OPTIONAL = "#7B8794"

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


def service(x, y, w, h, color, name, lines, *, dashed=False):
    """A service card: coloured header with the service name, white body with details.

    A dashed card is something that exists only when switched on (not part of the deployment)."""
    box(x, y, w, h, face="white", edge=color, lw=1.8, dash=(0, (5, 3)) if dashed else None, z=2)
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
        text(x + 0.14, y + h - 0.68 - i * step, line, size=10, color=MUTED if dashed else INK, z=6)


def arrow(points, *, color=LINE, dash=None, badge=None, badge_at=0, lw=1.9):
    xs = [p[0] for p in points]
    ys = [p[1] + Y0 for p in points]
    ax.plot(xs, ys, color=color, linewidth=lw, linestyle=dash or "-", zorder=4)
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
    "Region us-east-1 · as defined in infrastructure/terraform/ · API live on AWS Lambda, frontend on Vercel",
    fontsize=12.5,
    color=MUTED,
    va="center",
)

# ---- outside AWS: users, frontends, CI/CD (left) and the operator (right) ---------------------
service(0.3, 13.3, 3.1, 1.4, EXTERNAL, "User browser", ["Signs in, uploads a CSV,", "reviews results, predicts"])
service(0.3, 10.4, 3.1, 1.5, EXTERNAL, "Vercel", ["Next.js frontend (primary)", "Auto-deploys from GitHub"])
service(0.3, 8.5, 3.1, 1.3, OPTIONAL, "Amplify Hosting", ["Optional, off by default", "(enable_frontend)"], dashed=True)
service(0.3, 0.8, 3.1, 1.9, EXTERNAL, "GitHub Actions", ["deploy.yml, environment", "“production”; short-lived", "OIDC token, no AWS keys"])
service(24.0, 7.05, 3.0, 1.75, EXTERNAL, "Operator", ["AWS CLI + Session Manager", "plugin; creates users", "(no public sign-up)"])

# ---- AWS cloud ------------------------------------------------------------------------------
box(3.75, 0.3, 19.95, 15.4, face="#FBFBFD", edge="#232F3E", lw=2.2, radius=0.12, z=0)
text(3.95, 15.48, "AWS Cloud · us-east-1", size=14, weight="bold", color="#232F3E")

# Regional services strip (outside the VPC).
box(4.0, 13.05, 19.45, 2.05, face="#F3F5F7", edge="#9AA5B1", lw=1.2, dash="--", z=0)
text(4.15, 14.88, "Regional services (outside the VPC)", size=10.5, color=MUTED, style="italic")
service(4.1, 13.15, 3.5, 1.5, STORAGE, "Amazon S3", ["Datasets and models, AES-256", "Public access blocked, TLS only", "CORS for presigned uploads"])
service(7.85, 13.15, 3.5, 1.5, INTEGRATION, "Amazon SQS", ["automl-lab-experiments-queue", "Dead-letter queue after 3 tries", "SSE on, TLS-only policy"])
service(11.6, 13.15, 3.5, 1.5, SECURITY, "SSM Parameter Store", ["/automl-lab/db-password", "/automl-lab/jwt-secret", "Read by the worker at start"])
service(15.35, 13.15, 3.9, 1.5, COMPUTE, "Amazon ECR", ["automl-lab-backend (API + worker)", "Scan on push, keeps last 20", "AES-256"])
service(19.55, 13.15, 3.8, 1.5, MANAGEMENT, "CloudWatch alarms", ["queue-has-work: > 0 for 1 min", "queue-idle: 0 for 5 min", "on visible + in-flight messages"])

# Application Auto Scaling, between the alarms and the worker.
service(19.8, 9.0, 3.6, 1.6, MANAGEMENT, "App Auto Scaling", ["Worker desired count 0..1", "Step scaling: exactly 1 / 0", "Service-linked role (AWS)"])

# The API: a Lambda function behind a public Function URL, attached to the private subnets.
service(4.1, 8.6, 3.35, 2.6, COMPUTE, "AWS Lambda · API", ["automl-lab-api (image)", "FastAPI via Web Adapter", "Public HTTPS Function URL", "ENIs in the private subnets", "Secrets as encrypted env"])

# IAM / OIDC.
service(4.1, 0.6, 3.35, 2.6, SECURITY, "IAM · GitHub OIDC", ["OIDC provider and role", "automl-lab-github-deploy", "Only this repo and the", "“production” environment", "ECR push, Lambda and", "ECS roll-out"])

# VPC.
box(8.0, 0.55, 11.5, 11.85, face="#F7F4FF", edge=NETWORK, lw=2.4, radius=0.12, z=0)
text(9.2, 12.12, "VPC · automl-lab-vpc · 10.20.0.0/16", size=12, weight="bold", color=NETWORK)

# Internet gateway sits on the VPC border, above the worker.
box(14.65, 12.1, 1.9, 0.6, face=NETWORK, edge=NETWORK, z=6)
text(15.6, 12.4, "Internet gateway", size=10.5, color="white", weight="bold", ha="center", z=7)

# Public subnets.
box(8.3, 6.85, 10.9, 4.7, face="#EEF6EC", edge=STORAGE, lw=1.4, dash="--", z=0)
text(8.45, 11.33, "Public subnets", size=10.5, color="#3F6212", weight="bold")
text(8.45, 11.07, "10.20.0.0/24 · 10.20.1.0/24", size=9.5, color="#3F6212")
service(8.55, 8.6, 2.9, 2.2, NETWORK, "S3 gateway endpoint", ["On the public and", "private route tables;", "S3 traffic stays", "inside AWS"])
service(11.8, 8.6, 4.3, 2.2, COMPUTE, "ECS Fargate · worker", ["Cluster automl-lab-cluster", "Service automl-lab-worker", "0..1 tasks, autoscaled", "Runs python -m worker.main", "Public IP, no NAT gateway"])
service(16.45, 7.05, 2.55, 1.75, COMPUTE, "Admin task", ["One-off, worker image;", "ECS Exec runs", "app.cli create-user"])

# Private subnets.
box(8.3, 0.8, 10.9, 5.8, face="#EEF3FB", edge=DATABASE, lw=1.4, dash="--", z=0)
text(8.45, 6.35, "Private subnets", size=10.5, color="#2B3A9E", weight="bold")
text(8.45, 6.09, "10.20.10.0/24 · 10.20.11.0/24", size=9.5, color="#2B3A9E")
text(8.45, 5.83, "No route to the internet", size=9.5, color="#2B3A9E")
service(8.55, 2.6, 2.9, 2.1, COMPUTE, "Lambda ENIs", ["The API's network", "interfaces; security", "group: no inbound"])
service(11.8, 2.6, 3.1, 2.1, NETWORK, "SQS endpoint", ["Interface endpoint,", "private DNS, subnet a;", "links to Amazon SQS"])
service(15.3, 2.6, 3.65, 2.1, DATABASE, "Amazon RDS", ["PostgreSQL, db.t4g.micro", "20 GiB gp3, encrypted, TLS", "Reachable from the API and", "the worker only"])

# ---- arrows ---------------------------------------------------------------------------------
# 1 browser -> Vercel (Amplify is the optional alternative)
arrow([(1.85, 13.3), (1.85, 11.9)], badge=1)
# 2 frontend -> API Function URL
arrow([(3.4, 11.0), (4.1, 11.0)], badge=2, badge_at=0)
arrow([(3.4, 9.15), (4.1, 9.15)], color=OPTIONAL, dash=(0, (5, 3)))
# 3 browser -> S3 (presigned PUT)
arrow([(3.4, 14.0), (4.1, 14.0)], badge=3)
# 4 API -> its ENIs -> RDS, and -> SQS endpoint
arrow([(7.45, 9.4), (7.75, 9.4), (7.75, 3.65), (8.55, 3.65)], badge=4, badge_at=1)
arrow([(11.45, 3.65), (11.8, 3.65)])
arrow([(10.0, 2.6), (10.0, 1.5), (17.1, 1.5), (17.1, 2.6)])
# 5 SQS metrics -> CloudWatch alarms -> Application Auto Scaling -> worker
arrow([(9.6, 14.65), (9.6, 15.38), (21.45, 15.38), (21.45, 14.65)], dash=(0, (5, 3)), badge=5, badge_at=1)
arrow([(21.6, 13.15), (21.6, 10.6)])
arrow([(19.8, 9.8), (16.1, 9.8)])
# 6 worker -> SQS endpoint, RDS, S3 endpoint, internet gateway
arrow([(13.0, 8.6), (13.0, 4.7)])
number(13.0, 7.7, 6)
arrow([(15.7, 8.6), (15.7, 4.7)])
arrow([(11.8, 10.0), (11.45, 10.0)])
arrow([(15.6, 10.8), (15.6, 12.1)])
# internet gateway -> regional services (ECR image, SSM secrets, logs)
arrow([(15.6, 12.7), (15.6, 13.15)])
# S3 endpoint -> S3
arrow([(8.8, 10.8), (8.8, 12.75), (5.85, 12.75), (5.85, 13.15)])
# 7 GitHub -> IAM role -> Lambda
arrow([(3.4, 1.75), (4.1, 1.75)], badge=7)
arrow([(4.9, 3.2), (4.9, 8.6)], dash=(0, (5, 3)))
# 8 operator -> one-off admin task (ECS Exec) -> RDS
arrow([(24.0, 7.9), (19.0, 7.9)], badge=8)
arrow([(17.7, 7.05), (17.7, 4.7)])

# ---- legend ---------------------------------------------------------------------------------
ax.add_patch(Rectangle((0.3, 0.15), W - 0.6, 2.2, facecolor="white", edgecolor="#9AA5B1", linewidth=1.2, zorder=0))
legend = [
    (1, "The browser loads the Next.js UI from Vercel (Amplify Hosting is optional and off)."),
    (2, "The UI calls the API's Lambda Function URL over HTTPS with a bearer token."),
    (3, "The browser uploads a CSV straight to S3 with a presigned PUT URL."),
    (4, "The API reaches RDS and the SQS endpoint through its network interfaces."),
    (5, "SQS metrics drive two alarms; Application Auto Scaling sets the worker to 1 or 0 tasks."),
    (6, "The worker polls SQS, trains, writes S3 and RDS, then deletes the message."),
    (7, "GitHub Actions swaps its OIDC token for the deploy role, pushes to ECR, rolls out."),
    (8, "An operator creates users with app.cli create-user in a one-off ECS Exec task."),
]
for i, (n, s_) in enumerate(legend):
    col, row = divmod(i, 4)
    x = 0.6 + col * (W - 1.2) / 2
    y_abs = 2.05 - row * 0.36
    number(x, y_abs - Y0, n)
    text(x + 0.35, y_abs - Y0, s_, size=10.5)
text(
    W / 2,
    0.42 - Y0,
    "Dashed card: exists only when switched on (enable_frontend). The Lambda API and the worker exist when enable_compute = true; "
    "the worker runs 0..1 tasks with the queue (enable_worker_autoscaling). The worker reads the SSM secrets; the API gets them as encrypted env vars.",
    size=10,
    color=MUTED,
    style="italic",
    ha="center",
)

for out in (OUT, OUT.with_suffix(".svg")):
    fig.savefig(out, dpi=200, bbox_inches="tight", pad_inches=0.2, facecolor="white")
    print(f"wrote {out}")
