# Consent notice and worker script: DRAFT

**DRAFT. Not approved. Needs team and legal review (DPDP Act 2023) before use.** The periods below are the spec's defaults (§9, §8.11); if the config changes, this text must change with it.

Bracketed parts are for the team to fill in: [grievance officer], [contact], [organisation].

---

## Part 1: Consent notice (self-managed homes: app and WhatsApp)

### English

**Thandak: what we keep and why**

Thandak is free. You can use it without saving anything. If you turn on heat alerts or save your home, we keep:

- **Your area:** a square of about 10 km and your district. Never your exact location.
- **Your language and alert settings.**
- **About your home:** roof type, fan, cooler or AC, power cuts, water shortage, and your budget for fixes, if you tell us.
- **One yes/no:** whether someone at home needs extra care in the heat. We don't keep who it is, their age, health problems or medicines. Those stay on your phone.
- **Your phone number,** if you sign up on WhatsApp or SMS. It is stored locked (encrypted) and used only to send your alerts.
- **Room temperature readings and feedback,** if you send them.

**Why:** to send you heat alerts for your area and to give advice that fits your home.

**Anonymous counts:** only if you tick "share anonymous counts", we add your home to totals for government planning. Totals smaller than 10 homes are never shown.

**How long:**
- If you don't use Thandak for a year, we ask whether you want to keep alerts. If you don't reply, we delete your details.
- Readings are deleted after 2 years, and feedback after 90 days.
- After you delete your details, they also leave our backups within 14 days.

**Your choices:**
- Stop alerts and delete your details at any time: reply **STOP** on WhatsApp, or tap **Delete my data** in the app. It takes one step.
- Download everything we hold about you from the app.

**Questions or complaints:** [grievance officer name], [email], [phone].

Reply **YES** to agree and turn on alerts.

### Hindi

**ठंडक: हम क्या रखते हैं और क्यों**

ठंडक मुफ़्त है। आप कुछ भी सेव किए बिना इसे इस्तेमाल कर सकते हैं। अगर आप गर्मी के अलर्ट चालू करते हैं या अपना घर सेव करते हैं, तो हम ये रखते हैं:

- **आपका इलाक़ा:** लगभग 10 किमी का एक हिस्सा और आपका ज़िला। आपकी सही जगह कभी नहीं।
- **आपकी भाषा और अलर्ट की सेटिंग।**
- **आपके घर के बारे में:** छत किस तरह की है, पंखा, कूलर या AC, बिजली कटौती, पानी की कमी, और उपायों के लिए आपका बजट, अगर आप बताएँ।
- **एक हाँ/ना:** क्या घर में किसी को गर्मी में ख़ास ध्यान चाहिए। वह कौन है, उसकी उम्र, बीमारी या दवाएँ हम नहीं रखते। वे आपके फ़ोन में ही रहती हैं।
- **आपका फ़ोन नंबर,** अगर आप WhatsApp या SMS से जुड़ते हैं। यह ताले में (एन्क्रिप्ट करके) रखा जाता है और सिर्फ़ आपके अलर्ट भेजने में इस्तेमाल होता है।
- **कमरे के तापमान की रीडिंग और आपकी राय,** अगर आप भेजें।

**क्यों:** ताकि आपके इलाक़े के लिए गर्मी के अलर्ट भेज सकें और आपके घर के हिसाब से सलाह दे सकें।

**गिनती, बिना नाम के:** सिर्फ़ तब, जब आप "बिना नाम की गिनती साझा करें" चुनें, हम आपके घर को सरकारी योजना के लिए कुल गिनती में जोड़ते हैं। 10 से कम घरों वाली गिनती कभी नहीं दिखाई जाती।

**कब तक:**
- अगर आप एक साल तक ठंडक इस्तेमाल नहीं करते, तो हम पूछेंगे कि क्या आप अलर्ट चालू रखना चाहते हैं। जवाब न आने पर हम आपकी जानकारी मिटा देंगे।
- रीडिंग 2 साल बाद और आपकी राय 90 दिन बाद मिटा दी जाती है।
- जानकारी मिटाने के बाद, वह 14 दिन के अंदर हमारे बैकअप से भी हट जाती है।

**आपके हाथ में:**
- कभी भी अलर्ट बंद करें और अपनी जानकारी मिटाएँ: WhatsApp पर **STOP** लिखें, या ऐप में **मेरा डेटा मिटाएँ** दबाएँ। बस एक कदम।
- हमारे पास आपकी जो भी जानकारी है, वह ऐप से डाउनलोड करें।

**सवाल या शिकायत:** [शिकायत अधिकारी का नाम], [ईमेल], [फ़ोन]।

मंज़ूर हो तो **YES** लिखें, अलर्ट चालू हो जाएँगे।

---

## Part 2: Worker read-aloud script (worker-managed homes)

The worker reads this out in the family's language before saving anything, and saves `consent:{version, by:"worker", script_version}`. If the family has a phone, an SMS confirmation can follow.

Open question for the team: **children's data.** Before this script is used for homes with children, check what the DPDP Rules require for a child's details entered by a health worker (see `docs/TEAM_TODO.md`).

### English

"I'm [worker name] from [organisation]. I'd like to add your home to Thandak, a free heat-safety service, so I can check on your family on very hot days and tell you what to do.

If you agree, I will save:
- your area and district (not your exact address),
- your home: roof, fan, cooler or AC, power cuts and water,
- for the people at home, only an age group, whether someone is pregnant, health problems as a general type (for example 'heart'), and medicine types. No names of medicines. I can use a nickname instead of a real name.

These details are locked (encrypted). Only I and my organisation's supervisor can see them, and every time we look, it is recorded.

We use them only to plan heat safety for your family. Messages sent to your phone never mention anyone's health.

You can say no, and you can ask me at any time to delete everything. If you don't use the service for a year, it is deleted.

For questions or complaints: [grievance contact].

Do you agree?"

### Hindi

"मैं [कार्यकर्ता का नाम], [संस्था] से हूँ। मैं आपके घर को ठंडक में जोड़ना चाहती/चाहता हूँ। यह गर्मी से बचाव की मुफ़्त सेवा है, ताकि बहुत गर्म दिनों में मैं आपके परिवार का हाल ले सकूँ और बता सकूँ कि क्या करना है।

अगर आप मानें, तो मैं ये बातें सेव करूँगी/करूँगा:
- आपका इलाक़ा और ज़िला (आपका पूरा पता नहीं),
- आपका घर: छत, पंखा, कूलर या AC, बिजली कटौती और पानी,
- घर के लोगों के लिए सिर्फ़ उम्र का समूह, कोई गर्भवती है या नहीं, बीमारी किस तरह की है (जैसे 'दिल'), और दवा किस तरह की है। दवाओं के नाम नहीं। असली नाम की जगह घर का नाम भी चलेगा।

यह जानकारी ताले में (एन्क्रिप्ट करके) रहती है। इसे सिर्फ़ मैं और मेरी संस्था के सुपरवाइज़र देख सकते हैं, और हर बार देखने का रिकॉर्ड रहता है।

हम इसे सिर्फ़ आपके परिवार को गर्मी से बचाने की योजना के लिए इस्तेमाल करते हैं। आपके फ़ोन पर आने वाले संदेशों में किसी की सेहत की बात कभी नहीं होती।

आप मना कर सकते हैं, और कभी भी मुझसे सब कुछ मिटाने को कह सकते हैं। एक साल तक सेवा इस्तेमाल न होने पर जानकारी मिटा दी जाती है।

सवाल या शिकायत के लिए: [शिकायत का संपर्क]।

क्या आप मानते हैं?"
