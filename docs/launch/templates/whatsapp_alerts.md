# WhatsApp alert templates: DRAFT

**DRAFT. Not approved. Don't submit or send until the team approves the wording.**

Rules for every template (spec §2 rule 7, §7.6):
- No health details: no conditions, medicines, pregnancy or names.
- No numbers typed into the text. Every value is a variable filled from the forecast or from `verified_numbers.csv`.
- `{action}` is one action line from the fix catalogue (`fixes.json`), in the same language, already approved.
- Nothing is sent between 22:00 and 06:00 IST.

Variables:

| Variable | Filled from | Example (English / Hindi) |
|---|---|---|
| `{district}` | the household's district | Jaipur / जयपुर |
| `{level}` | tomorrow's (or today's) heat level word | Extreme / बहुत ज़्यादा |
| `{day}` | "Tomorrow" or "Today" | Tomorrow / कल |
| `{from}`, `{to}` | the hottest work hours, from the forecast | 12:00, 16:00 |
| `{action}` | one approved action line | Keep windows and curtains shut from noon. / दोपहर से खिड़की और पर्दे बंद रखें। |

## 1. Evening alert (`evening_alert`), category Utility

**English**
> Thandak: {day}, {level} heat in {district}. {action} Reply HELP for tips, STOP to stop alerts.

**Hindi**
> ठंडक: {day} {district} में {level} गर्मी रहेगी। {action} सलाह के लिए HELP, अलर्ट बंद करने के लिए STOP लिखें।

## 2. Morning work alert (`morning_work_alert`), category Utility

Sent at 06:30 to homes that set an outdoor work window, when today is hot during it.

**English**
> Thandak: Today, {level} heat in {district} from {from} to {to}. {action} Reply STOP to stop alerts.

**Hindi**
> ठंडक: आज {district} में {from} से {to} बजे तक {level} गर्मी रहेगी। {action} अलर्ट बंद करने के लिए STOP लिखें।

## 3. Reply to STOP (`stop_reply`)

Sent inside the 24-hour service window, so it doesn't need template approval. Two versions, because STOP deletes the household when it has no other channel (spec §6.5).

**English, details deleted**
> Done. Thandak alerts are off and your saved details have been deleted. To start again, send HI.

**English, other channel still active**
> Done. Thandak WhatsApp alerts are off. Your other alert settings stay as they are. To start again, send HI.

**Hindi, details deleted**
> हो गया। ठंडक के अलर्ट बंद हो गए हैं और आपकी जानकारी मिटा दी गई है। फिर से शुरू करने के लिए HI भेजें।

**Hindi, other channel still active**
> हो गया। ठंडक के WhatsApp अलर्ट बंद हो गए हैं। बाक़ी अलर्ट पहले जैसे रहेंगे। फिर से शुरू करने के लिए HI भेजें।

## 4. Reply to HELP (`help_reply`)

**English**
> Thandak sends one heat alert the evening before a hot day in your area.
> ALERT: today's heat level now
> PIN: change your area
> STOP: stop alerts and delete your details
> In an emergency, call {emergency_number}.

**Hindi**
> ठंडक आपके इलाक़े में गर्म दिन से एक शाम पहले गर्मी का अलर्ट भेजता है।
> ALERT: अभी आज की गर्मी का स्तर
> PIN: अपना इलाक़ा बदलें
> STOP: अलर्ट बंद करें और अपनी जानकारी मिटाएँ
> इमरजेंसी में {emergency_number} पर कॉल करें।

`{emergency_number}` is 112 (NCDC 2026 advisory, already in the app), plus the state ambulance number only where its row in `data/emergency_numbers.csv` is Verified.

## 5. Retention check (`retention_keep`), category Utility

Sent 30 days before an inactive home is deleted (spec §9).

**English**
> Thandak: you haven't used Thandak for a while. Reply YES to keep getting heat alerts for {district}. If we don't hear from you, your details will be deleted.

**Hindi**
> ठंडक: आपने काफ़ी समय से ठंडक इस्तेमाल नहीं किया है। {district} के लिए गर्मी के अलर्ट पाते रहने के लिए YES लिखें। जवाब न आने पर आपकी जानकारी मिटा दी जाएगी।
