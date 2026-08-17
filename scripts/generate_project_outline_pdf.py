from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "pdf"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PDF_PATH = OUT_DIR / "GreenRoute_AI_Project_Outline.pdf"


def p(text, style):
    return Paragraph(text, style)


def bullet(text, style):
    return Paragraph(f"- {text}", style)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D7DEE8"))
    canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#667085"))
    canvas.drawString(18 * mm, 9 * mm, "GreenRoute AI - SEA Engineering Design Competition 2026")
    canvas.drawRightString(192 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="TitleMain",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#12343B"),
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Subtitle",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#475467"),
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#155E63"),
            spaceBefore=10,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Body",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.4,
            leading=12.4,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#1F2937"),
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.3,
            leading=10.5,
            textColor=colors.HexColor("#344054"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableHeader",
            parent=styles["Small"],
            fontName="Helvetica-Bold",
            fontSize=8.2,
            leading=10.2,
            textColor=colors.white,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableCell",
            parent=styles["Small"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=10.2,
            textColor=colors.HexColor("#1F2937"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="ProjectBullet",
            parent=styles["Body"],
            leftIndent=12,
            firstLineIndent=-8,
            bulletIndent=0,
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Callout",
            parent=styles["Body"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#12343B"),
            backColor=colors.HexColor("#EAF6F6"),
            borderColor=colors.HexColor("#B5D8D8"),
            borderWidth=0.5,
            borderPadding=6,
            spaceAfter=8,
        )
    )

    def table_rows(data):
        rows = []
        for row_index, row in enumerate(data):
            style = styles["TableHeader"] if row_index == 0 else styles["TableCell"]
            rows.append([p(str(cell), style) for cell in row])
        return rows

    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=A4,
        rightMargin=17 * mm,
        leftMargin=17 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title="GreenRoute AI Project Outline",
        author="Design Competition Team",
    )

    story = []

    story.append(p("GreenRoute AI", styles["TitleMain"]))
    story.append(
        p(
            "Smart Bin Monitoring, Predictive Collection Optimisation, Recycling Classification, and Citizen Incentives",
            styles["Subtitle"],
        )
    )
    story.append(
        p(
            "<b>Competition:</b> Southeast Asia Engineering Design Competition 2026 | "
            "<b>Theme:</b> Sustainability and AI for Real-World Problem Solving | "
            "<b>Domain:</b> Urban Waste and Recycling Management",
            styles["Small"],
        )
    )
    story.append(Spacer(1, 4))
    story.append(
        p(
            "GreenRoute AI is a low-cost smart urban waste management system that predicts bin overflow risk, "
            "uses multimodal priority scoring, optimises collection routes, and gathers QR citizen feedback. "
            "The main engineering core is Focus A + C, with Focus B + D integrated through the recycling return bin.",
            styles["Callout"],
        )
    )

    story.append(p("1. Problem Statement", styles["Section"]))
    story.append(
        p(
            "Urban waste collection in Southeast Asia is often reactive and schedule-driven. Fixed collection cycles "
            "do not account for fast-changing waste generation caused by night markets, schools, festivals, weekends, "
            "commercial areas, and road disruptions. This can lead to overflowing bins, illegal dumping, unnecessary "
            "truck trips, higher fuel use, CO2 emissions, and poor visibility for municipal operators.",
            styles["Body"],
        )
    )

    story.append(p("2. Proposed Solution", styles["Section"]))
    story.append(
        p(
            "Each smart bin uses an ultrasonic sensor mounted at the top and a weight sensor/load cell to estimate fill "
            "level. Data is sent through ESP32/Arduino nodes to a central dashboard, while QR feedback lets residents "
            "report overflow, odour, contamination, or blocked access. A time-series machine learning model predicts "
            "future fill level and overflow risk. A route optimiser then prioritises bins using a multimodal score "
            "that combines current fill, weight trend, predicted fill rate, location, time of day, event surge, "
            "citizen reports, truck distance, road closure status, and maintenance alerts.",
            styles["Body"],
        )
    )
    story.append(
        p(
            "A recycling return bin extends the system by allowing citizens to authorize themselves, insert bottles or "
            "cans, receive item classification, and earn a simulated digital refund through e-wallet credit, QR transfer, "
            "bank transfer, or reward points.",
            styles["Body"],
        )
    )

    story.append(p("3. Focus Area Mapping", styles["Section"]))
    focus_data = [
        ["Focus Area", "Project Implementation"],
        ["A - Smart Bin Monitoring", "Ultrasonic + weight sensing, ESP32 data transmission, overflow prediction dashboard."],
        ["B - AI Waste Classification", "Return-bin model classifies PET bottle, glass bottle, aluminium can, or rejected item."],
        ["C - Predictive Collection Optimisation", "Risk-weighted route optimisation with event surge and road closure rerouting."],
        ["D - Citizen Engagement", "QR/app authorization, QR issue reports, digital refunds, reward points, recycling impact dashboard."],
    ]
    focus_table = Table(table_rows(focus_data), colWidths=[42 * mm, 128 * mm], repeatRows=1)
    focus_table.setStyle(table_style())
    story.append(focus_table)

    story.append(p("4. System Architecture", styles["Section"]))
    story.append(
        p(
            "Smart Bin -> ESP32/Arduino -> Laptop/Raspberry Pi/Cloud Platform -> Prediction AI -> Priority Scoring "
            "-> Route Optimizer -> Municipal Dashboard",
            styles["Callout"],
        )
    )
    for item in [
        "Ultrasonic sensor estimates empty space from lid to waste surface.",
        "Weight sensor improves fill estimation when waste shape makes height readings unreliable.",
        "Dashboard displays live fill level, predicted overflow, QR citizen alerts, maintenance alerts, recycling returns, and route recommendation.",
        "Multimodal priority score combines fill level, weight trend, predicted fill rate, citizen reports, event surge, truck distance, and road access.",
        "Road-closure rerouting is simulated through dashboard toggles, inspired by Waze-style navigation intelligence.",
    ]:
        story.append(bullet(item, styles["ProjectBullet"]))

    story.append(PageBreak())

    story.append(p("5. Prototype Scope", styles["Section"]))
    proto_data = [
        ["Prototype Element", "Planned Implementation"],
        ["Street model", "1:20 street block with at least 3 instrumented smart bins and one model collection truck."],
        ["Sensors", "Top-mounted ultrasonic sensor on each bin; load cell/weight sensor where budget allows; QR feedback label on each bin."],
        ["Return bin", "Authorized bottle/can return, camera-based classification, digital refund simulation."],
        ["Outputs", "LED status, dashboard route display, overflow countdown, maintenance alerts, recycling metrics."],
        ["Safety/budget", "Prototype under 12 V DC, target below 10 W continuous, hardware cap USD 150 / SGD 200."],
    ]
    proto_table = Table(table_rows(proto_data), colWidths=[42 * mm, 128 * mm], repeatRows=1)
    proto_table.setStyle(table_style())
    story.append(proto_table)

    story.append(p("6. AI and Routing Method", styles["Section"]))
    story.append(
        p(
            "<b>Fill prediction:</b> train a lightweight time-series model using current fill level, fill-rate trend, "
            "hour, day of week, bin location, event flags, road closure status, maintenance status, and recent collection history. "
            "Candidate models include a linear-regression baseline, Random Forest Regressor, and XGBoost/gradient boosting.",
            styles["Body"],
        )
    )
    story.append(
        p(
            "<b>Priority score:</b> current fill level + weight trend + predicted fill increase + event surge factor "
            "+ citizen report urgency + truck distance + time since last collection + location importance - maintenance penalty.",
            styles["Body"],
        )
    )
    story.append(
        p(
            "<b>Route optimisation:</b> Dijkstra or A* can calculate shortest paths between map nodes, while OR-Tools VRP/CVRP "
            "or a priority-based planner can select the collection order under capacity, distance, and road-closure constraints.",
            styles["Body"],
        )
    )

    story.append(p("7. Recycling Return Workflow", styles["Section"]))
    workflow = [
        "Citizen scans QR code, uses app login/RFID, or enters a simulated user ID.",
        "Return bin becomes ready and the citizen inserts a bottle or can.",
        "Trained model classifies the item as PET bottle, glass bottle, aluminium can, or rejected item.",
        "Accepted item updates the return count and simulated digital refund value.",
        "Rejected item triggers an invalid-item alert.",
        "Recycling-bin fill level updates and may increase collection priority.",
    ]
    for item in workflow:
        story.append(bullet(item, styles["ProjectBullet"]))

    story.append(p("8. Simulation Plan", styles["Section"]))
    story.append(
        p(
            "The digital simulation will model 500 households and 20 commercial units over 30 days. It will compare a "
            "fixed-schedule baseline against GreenRoute AI's predictive collection strategy using reproducible random seeds "
            "and confidence intervals across repeated runs. Scenarios will include weekday/weekend "
            "patterns, school-day effects, night-market surges, event/festival surges, road closures, maintenance faults, and "
            "recycling return-bin fill changes.",
            styles["Body"],
        )
    )
    kpi_data = [
        ["KPI", "What It Shows"],
        ["Overflow incidents", "Target at least 40% fewer public bin overflows."],
        ["Collection trips", "Target at least 25% fewer unnecessary truck dispatches."],
        ["Route distance / fuel use", "Operational cost and travel-efficiency improvement."],
        ["Estimated CO2 reduction", "Target at least 20% lower collection-related emissions."],
        ["Average fill level at pickup", "Whether collections happen at the right time."],
        ["Recyclable cleanliness", "Target at least 15% cleaner recyclables using accepted/rejected item alerts."],
        ["Classification accuracy", "Return-bin model reliability for PET/glass/can/rejected classes."],
        ["Digital refunds issued", "Citizen engagement and recycling participation."],
    ]
    kpi_table = Table(table_rows(kpi_data), colWidths=[48 * mm, 122 * mm], repeatRows=1)
    kpi_table.setStyle(table_style())
    story.append(kpi_table)

    story.append(p("9. Budget Strategy", styles["Section"]))
    budget_data = [
        ["Component", "Budget Approach"],
        ["ESP32/Arduino nodes", "Use low-cost boards for 3 smart bins."],
        ["Ultrasonic sensors", "One top-mounted sensor per bin."],
        ["Load cells + HX711", "Use 1-3 modules depending on final cost."],
        ["Camera/webcam", "Use existing laptop webcam where possible for classification."],
        ["Dashboard/simulation", "Run on laptop; software tools do not count against hardware cap."],
        ["Model materials", "Use recycled cardboard/acrylic and low-cost props."],
    ]
    budget_table = Table(table_rows(budget_data), colWidths=[48 * mm, 122 * mm], repeatRows=1)
    budget_table.setStyle(table_style())
    story.append(budget_table)

    story.append(p("10. Sustainability and SDG Alignment", styles["Section"]))
    for item in [
        "SDG 11: reduces overflow incidents and improves cleanliness in dense urban communities.",
        "SDG 12: improves recycling participation through deposit-return incentives and accepted-item classification.",
        "SDG 13: reduces route distance, fuel consumption, and collection-related CO2 emissions.",
        "SDG 9: demonstrates scalable smart-city infrastructure using low-cost sensors, AI, and dashboards.",
    ]:
        story.append(bullet(item, styles["ProjectBullet"]))

    story.append(p("11. Why It Can Win", styles["Section"]))
    story.append(
        p(
            "GreenRoute AI is stronger than a simple fill-level bin because it combines visible hardware, "
            "team-trained prediction AI, multimodal priority scoring, QR citizen feedback, a baseline-controlled "
            "simulation, and a realistic municipal adoption story. Judges can see the prototype working, then verify "
            "the impact through measurable overflow, trip, CO2, and recycling-quality targets.",
            styles["Body"],
        )
    )

    story.append(p("12. Scope Control", styles["Section"]))
    story.append(
        p(
            "The project deliberately avoids high-risk extras such as Gaussian splatting for volume estimation, physical coin payout, "
            "full city traffic integration, and general-purpose classification of all waste. The buildable prototype focuses on "
            "ultrasonic + weight sensing, predictive routing, dashboard decision support, and a controlled bottle/can return module.",
            styles["Body"],
        )
    )

    story.append(p("Sources", styles["Section"]))
    for source in [
        "World Bank, What a Waste 3.0 - https://www.worldbank.org/en/publication/what-a-waste",
        "Google OR-Tools Vehicle Routing - https://developers.google.com/optimization/routing",
        "LoRa Alliance, About LoRaWAN - https://lora-alliance.org/about-lorawan/",
        "Singapore NEA Beverage Container Return Scheme - https://www.nea.gov.sg/our-services/waste-management/beverage-container-return-scheme",
        "Ireland Re-turn Deposit Return Scheme - https://re-turn.ie/",
    ]:
        story.append(p(source, styles["Small"]))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def table_style():
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#155E63")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.2),
            ("LEADING", (0, 0), (-1, -1), 10.2),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#1F2937")),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FAFC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
    )


if __name__ == "__main__":
    build_pdf()
    print(PDF_PATH)
