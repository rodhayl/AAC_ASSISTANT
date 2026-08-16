# Pilot and Evaluation Guide

> **Important Notice:** AAC Assistant is open-source assistive technology software and **has not yet undergone formal clinical validation or medical device certification**. This guide is provided for educators, speech-language pathologists (SLPs), occupational therapists, and caregivers who wish to conduct structured exploratory trials or pilot evaluations in educational or home environments.

---

## 1. Purpose of an Evaluation

The goal of an AAC Assistant pilot evaluation is to assess:
1. **Communication Effectiveness:** How easily AAC users can navigate boards, select symbols, and construct sentence strips.
2. **Vocabulary & Learning Progression:** How effectively students engage with adaptive symbol identification exercises.
3. **Accessibility & Ergonomics:** How well the interface adapts to motor, visual, and cognitive needs (e.g., dwell time, touch target sizes, contrast themes, and reduced motion).
4. **Offline Reliability:** Seamless operation on local hardware without depending on cloud infrastructure.

---

## 2. Recommended Evaluator Profiles

- **Speech-Language Pathologists (SLPs):** Evaluating vocabulary organization, core word accessibility, and symbol clarity.
- **Special Education Teachers:** Evaluating classroom engagement, learning module utility, and customized board assignment.
- **Occupational Therapists:** Evaluating motor access, touch accuracy, dwell-time thresholds, and keyboard/switch navigation.
- **Caregivers and AAC Communicators:** Evaluating real-world communicative intent, speech output comprehension, and ease of daily use.

---

## 3. Pre-Pilot Setup Checklist

1. **Hardware Preparation:** Standard Windows 10/11 laptop, desktop, or touchscreen tablet (or Linux/macOS source installation).
2. **Installation:** Install via `AAC_Assistant_Setup_2.0.0.exe` or portable onedir distribution.
3. **Initial Security Setup:**
   - Launch application on first run (`http://127.0.0.1:8086/setup`).
   - Create a strong administrator password.
   - Verify loopback network binding (`127.0.0.1` by default).
4. **Data Initialization:**
   - Use demonstration accounts (`AAC_SEED_SAMPLE_DATA=true`) or create test student accounts with **pseudonyms/fictional identifiers** (e.g. `student_alpha`).
   - Pre-configure relevant communication boards and speech synthesis voices in Settings.
5. **Offline Verification:** Disconnect device from Wi-Fi/Ethernet to confirm that core communication, speech output, and symbol search operate 100% offline.

---

## 4. Privacy & Data Protection Safeguards

> [!CAUTION]
> **Strict Data Boundary:** Under no circumstances should personal health information (PHI), clinical diagnoses, medical records, government ID numbers, or real student full names be entered into test instances or collected during pilot feedback.

### Privacy Rules for Evaluators:
- **Use Pseudonyms:** Assign anonymous identifiers (e.g. `Participant-01`, `Student-A`) for all user profiles.
- **Local Data Retention:** All SQLite database records, uploaded symbols, and session statistics remain exclusively on the local testing machine.
- **Zero Telemetry:** The application transmits zero telemetry or analytics. Feedback must be collected manually by the evaluator.
- **Safe Feedback Submission:** When submitting qualitative feedback or bug reports, scrub all screenshots and logs of private communication phrases.

---

## 5. Structured Feedback Questionnaire

Evaluators may use the following categories to record qualitative and quantitative observations:

### A. Functional Communication
- [ ] Were core symbols easy to locate within 1–2 navigation steps?
- [ ] Did the sentence strip correctly accumulate selected symbols?
- [ ] Was the audio text-to-speech output loud, intelligible, and well-timed?
- [ ] Did custom symbol uploads maintain high clarity on the board grid?

### B. Adaptive Learning Modules
- [ ] Were question prompts clear and appropriately leveled for the participant?
- [ ] Did multi-modal visual and audio feedback reinforce correct answers?
- [ ] Did the student maintain engagement throughout a 5–10 minute learning session?

### C. Accessibility & Usability
- [ ] Did the participant require adjustments to dwell-time (press-and-hold) selection?
- [ ] Was high-contrast mode or dark mode beneficial for visual clarity?
- [ ] Was the interface comfortable with `prefers-reduced-motion` enabled?
- [ ] Were touch targets sufficiently spaced to prevent accidental adjacent clicks?

### D. System Reliability & Performance
- [ ] Did the application start quickly without unexpected error banners?
- [ ] Did speech playback respond with zero noticeable latency?
- [ ] Did the local SQLite storage preserve all created boards and progress across restarts?

---

## 6. Feedback & Issue Reporting

- **Bug Reports & Usability Feedback:** Submit issues via [GitHub Issues](https://github.com/rodhayl/AAC_ASSISTANT/issues) using the [Accessibility Report](../.github/ISSUE_TEMPLATE/accessibility_report.yml) or Bug Report template.
- **Security Vulnerabilities:** Submit privately via [GitHub Private Vulnerability Reporting](https://github.com/rodhayl/AAC_ASSISTANT/security/advisories/new).

---

## 7. Exit and Data Rollback Procedure

When completing or concluding a pilot evaluation:
1. **Export Configurations:** If custom boards or symbols were created, export them via Settings > Data Management.
2. **Local Data Removal:**
   - To completely reset local data, delete the application data directory (`%APPDATA%\AACAssistant` on Windows for installed copies) or uninstall via Windows Add/Remove Programs with the clean-data option.
   - For source installations, delete the local `data/` and `uploads/` directories.
