# SMS templates for DLT registration: DRAFT

**DRAFT. Not approved. Don't register or send until the team approves the wording.**

The same messages as `whatsapp_alerts.md`, in DLT format. Each `{#var#}` is a DLT variable, which holds up to 30 characters.

Rules (spec §2 rule 7, §7.6): no health details; no numbers typed into the text; nothing sent 22:00–06:00 IST.

**Length:** English (GSM) fits 160 characters in one SMS, or 153 per part when split. **Hindi is Unicode: 70 characters in one SMS, 67 per part.** So the Hindi versions are cut down to fit two parts at most, with the action line left out. The app link carries the details.

| Template | Language | Text | Variables | Approx. length (with typical values) |
|---|---|---|---|---|
| `evening_alert` | English | Thandak: {#var#}, {#var#} heat in {#var#}. {#var#} Reply STOP to stop alerts. | day, level, district, action | 110–150 (1 part) |
| `evening_alert` | Hindi | ठंडक: {#var#} {#var#} में {#var#} गर्मी रहेगी। अलर्ट बंद करने के लिए STOP लिखें। | day, district, level | 65–80 (1–2 parts) |
| `morning_work_alert` | English | Thandak: Today, {#var#} heat in {#var#} from {#var#} to {#var#}. {#var#} Reply STOP to stop alerts. | level, district, from, to, action | 120–155 (1–2 parts) |
| `morning_work_alert` | Hindi | ठंडक: आज {#var#} में {#var#} से {#var#} बजे तक {#var#} गर्मी रहेगी। STOP लिखकर अलर्ट बंद करें। | district, from, to, level | 70–90 (2 parts) |
| `otp` | English | {#var#} is your Thandak code. It expires in {#var#} minutes. Don't share it with anyone. | code, minutes | about 85 (1 part) |
| `otp` | Hindi | {#var#} आपका ठंडक कोड है। यह {#var#} मिनट में ख़त्म हो जाएगा। इसे किसी को न बताएँ। | code, minutes | about 65 (1 part) |
| `stop_reply` | English | Thandak SMS alerts are off. To start again, use the Thandak app or send HI on WhatsApp. | none | about 90 (1 part) |
| `stop_reply` | Hindi | ठंडक के SMS अलर्ट बंद हो गए हैं। फिर से शुरू करने के लिए ठंडक ऐप इस्तेमाल करें या WhatsApp पर HI भेजें। | none | about 95 (2 parts) |

Notes for registration:
- Register the English and Hindi versions as separate templates. DLT matches the exact text, including spaces and punctuation.
- The OTP expiry minutes come from config (spec §5.5: 10 minutes), passed as a variable so the text never hard-codes it.
- The STOP keyword on SMS needs the provider's two-way (inbound) number. If it isn't available, the SMS templates must say how to stop instead (e.g. "in the app"); decide with the provider.
