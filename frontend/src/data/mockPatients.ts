export interface PatientQueueItem {
  id: string;
  name: string;
  mrn: string;
  post_op_day: number;
  procedure: string;
  tier: "emergency" | "critical" | "review" | "missed";
  reasons: { text: string; isSevere?: boolean }[];
  alert_id?: string | null;
  alert_age_text: string;
  sla_text: string;
  acknowledged: boolean;
  acknowledged_text?: string;
  action_type: "call" | "acknowledge" | "ping" | "none";
}

export const INITIAL_PATIENTS: PatientQueueItem[] = [
  {
    id: "9042",
    name: "H. Thorne",
    mrn: "ER-9042",
    post_op_day: 4,
    procedure: "Left TKA",
    tier: "emergency",
    reasons: [
      { text: "Calf swelling & acute sharp pain", isSevere: true },
      { text: "Suspected DVT trigger", isSevere: true }
    ],
    alert_id: "alert-9042",
    alert_age_text: "3m ago",
    sla_text: "12m SLA remains",
    acknowledged: false,
    action_type: "call"
  },
  {
    id: "8819",
    name: "M. Vance",
    mrn: "ER-8819",
    post_op_day: 2,
    procedure: "Bilateral TKA",
    tier: "critical",
    reasons: [
      { text: "Wound incision exudate reported", isSevere: false },
      { text: "Fever returned: 38.6°C", isSevere: true }
    ],
    alert_id: "alert-8819",
    alert_age_text: "8m ago",
    sla_text: "7m SLA remains",
    acknowledged: false,
    action_type: "acknowledge"
  },
  {
    id: "7630",
    name: "R. Nair",
    mrn: "ER-7630",
    post_op_day: 9,
    procedure: "Right TKA",
    tier: "critical",
    reasons: [
      { text: "Persistent extension block >15°", isSevere: false },
      { text: "Severe night pain flare", isSevere: false }
    ],
    alert_id: "alert-7630",
    alert_age_text: "11m ago",
    sla_text: "4m SLA remains",
    acknowledged: false,
    action_type: "acknowledge"
  },
  {
    id: "6102",
    name: "E. Alverez",
    mrn: "ER-6102",
    post_op_day: 14,
    procedure: "Right TKA",
    tier: "review",
    reasons: [
      { text: "Analgesic intolerance / nausea", isSevere: false },
      { text: "ROM flexion deficit at 65°", isSevere: false }
    ],
    alert_id: "alert-6102",
    alert_age_text: "24m ago",
    sla_text: "SLA logged",
    acknowledged: true,
    acknowledged_text: "Ack by Nurse Sarah J. (10m ago)",
    action_type: "none"
  },
  {
    id: "7115",
    name: "D. Gallagher",
    mrn: "ER-7115",
    post_op_day: 7,
    procedure: "Left TKA",
    tier: "review",
    reasons: [
      { text: "Mild peripatellar erythema spreading 1cm", isSevere: false }
    ],
    alert_id: "alert-7115",
    alert_age_text: "42m ago",
    sla_text: "SLA logged",
    acknowledged: true,
    acknowledged_text: "Ack by Dr. K. Mehta",
    action_type: "none"
  },
  {
    id: "5541",
    name: "A. Chen",
    mrn: "ER-5541",
    post_op_day: 21,
    procedure: "Right TKA",
    tier: "review",
    reasons: [
      { text: "Reported fall without direct knee impact", isSevere: false }
    ],
    alert_id: "alert-5541",
    alert_age_text: "1h 15m ago",
    sla_text: "SLA logged",
    acknowledged: true,
    acknowledged_text: "Ack by Nurse Sarah J.",
    action_type: "none"
  },
  {
    id: "8204",
    name: "B. Kowalski",
    mrn: "ER-8204",
    post_op_day: 5,
    procedure: "Left TKA",
    tier: "missed",
    reasons: [
      { text: "No check-in for 2 expected cycles (WhatsApp inactive 18h)", isSevere: false }
    ],
    alert_id: null,
    alert_age_text: "2h ago",
    sla_text: "2 overdue cycles",
    acknowledged: false,
    action_type: "ping"
  }
];
