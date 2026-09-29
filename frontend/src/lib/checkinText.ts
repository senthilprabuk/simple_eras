/**
 * What the patient check-in says, in the three languages patients enrol in.
 * Questions, measure names and answer options come from the server in the
 * patient's language; this is the page's own wording around them.
 *
 * The Tamil and Hindi are draft translations for demonstration. PRD NFR-6
 * requires professional translation before patients rely on them.
 */

export type CheckInLanguage = "en" | "ta" | "hi";

export const CHECKIN_LANGUAGES: { code: CheckInLanguage; label: string }[] = [
  { code: "en", label: "English" },
  { code: "ta", label: "தமிழ்" },
  { code: "hi", label: "हिन्दी" },
];

/** Emergency services on any mobile phone in India, and in most other countries. */
export const EMERGENCY_SERVICES = "112";

export interface CheckInText {
  locale: string;
  language: string;
  loading: string;
  openFromWhatsAppTitle: string;
  openFromWhatsAppBody: string;
  linkErrorTitle: string;
  linkErrorAdvice: string;
  backendUnavailable: string;
  greeting: string;
  dayAfterSurgery: (day: number) => string;
  alreadyCheckedIn: string;
  checkInReady: string;
  overview: (questions: number, steps: number, hospital: string) => string;
  startCheckIn: string;
  checkInAgain: string;
  goBack: string;
  stepOf: (step: number, of: number) => string;
  continue: string;
  sendToCareTeam: string;
  sending: string;
  answeredOf: (answered: number, total: number) => string;
  sections: Record<string, string>;
  checksIntro: string;
  photoStep: string;
  reviewStep: string;
  answerRequired: string;
  pleaseAnswer: string;
  skippedPrompt: (names: string) => string;
  answerThem: string;
  continueWithout: string;
  urgentTitle: string;
  urgentWithWard: (symptoms: string, hospital: string) => string;
  urgentNoWard: (symptoms: string) => string;
  callWard: string;
  call112: string;
  and: string;
  photoHint: string;
  photoAlt: string;
  remove: string;
  takePhoto: string;
  orGallery: string;
  photoNotSent: string;
  couldNotSend: string;
  edit: string;
  woundPhoto: string;
  noPhoto: string;
  notAnswered: string;
  yes: string;
  no: string;
  alreadySent: string;
  checkInSent: string;
  alreadySentBody: string;
  answersRecorded: (count: number, day: number) => string;
  replacesEarlier: string;
  urgentDone: string;
  whatsappSent: string;
  whatsappQueued: string;
  reference: string;
  received: string;
  startAgain: string;
  tapToEnter: string;
  tapToEdit: string;
  decrease: (name: string) => string;
  increase: (name: string) => string;
  typeValue: (name: string) => string;
  painHint: (min: number, max: number) => string;
  /** No pain, mild, uncomfortable, moderate, severe, worst possible. */
  painLevels: readonly [string, string, string, string, string, string];
  outOf: (score: number, max: number) => string;
}

const EN: CheckInText = {
  locale: "en-IN",
  language: "Language",
  loading: "Loading check-in…",
  openFromWhatsAppTitle: "Open your check-in from WhatsApp",
  openFromWhatsAppBody: "Today's check-in opens from the link in your WhatsApp reminder from the hospital.",
  linkErrorTitle: "This link can't be opened",
  linkErrorAdvice: "If this keeps happening, please use the link in your latest WhatsApp reminder.",
  backendUnavailable: "Backend unavailable",
  greeting: "Hello,",
  dayAfterSurgery: (day) => `Day ${day} after surgery`,
  alreadyCheckedIn: "You've already checked in today",
  checkInReady: "Today's check-in is ready",
  overview: (q, s, h) => `${q} questions across ${s} steps. Your care team at ${h} reviews every answer.`,
  startCheckIn: "Start today's check-in",
  checkInAgain: "Check in again",
  goBack: "Go back",
  stepOf: (step, of) => `Step ${step} of ${of}`,
  continue: "Continue",
  sendToCareTeam: "Send to my care team",
  sending: "Sending…",
  answeredOf: (a, n) => `${a} of ${n} questions answered`,
  sections: { readings: "Your readings", checks: "Symptom checks", progress: "Getting moving" },
  checksIntro: "Since yesterday, have you noticed any of these?",
  photoStep: "Wound photo",
  reviewStep: "Check and send",
  answerRequired: "Please answer each question marked in red.",
  pleaseAnswer: "Please answer this question",
  skippedPrompt: (names) => `You haven't answered: ${names}. Your care team will see these as not answered.`,
  answerThem: "Answer them",
  continueWithout: "Continue without them",
  urgentTitle: "Please call us now",
  urgentWithWard: (s, h) =>
    `You told us about ${s}. Do not wait for this check-in to be reviewed: call ${h} now. If you cannot get through, call emergency services on ${EMERGENCY_SERVICES}.`,
  urgentNoWard: (s) =>
    `You told us about ${s}. Do not wait for this check-in to be reviewed: call your hospital now. If you cannot reach them, call emergency services on ${EMERGENCY_SERVICES}.`,
  callWard: "Call the ward",
  call112: `Call emergency services (${EMERGENCY_SERVICES})`,
  and: " and ",
  photoHint: "Hold your phone about 30 cm from the wound in good light.",
  photoAlt: "Wound photo you selected",
  remove: "Remove",
  takePhoto: "Take a photo",
  orGallery: "or choose one from your gallery",
  photoNotSent: "For now the photo stays on this phone; it is not sent with your check-in.",
  couldNotSend: "Could not send",
  edit: "Edit",
  woundPhoto: "Wound photo",
  noPhoto: "No photo added",
  notAnswered: "Not answered",
  yes: "Yes",
  no: "No",
  alreadySent: "Already sent",
  checkInSent: "Check-in sent",
  alreadySentBody: "This check-in had already reached us, so nothing was duplicated.",
  answersRecorded: (n, d) => (n === 1 ? `1 answer recorded for day ${d}.` : `${n} answers recorded for day ${d}.`),
  replacesEarlier: "This replaces the earlier check-in you sent today.",
  urgentDone:
    "You reported a symptom that needs attention today. If you have not spoken to the ward yet, please call now.",
  whatsappSent: "A WhatsApp message confirming this check-in has been sent to you.",
  whatsappQueued: "A WhatsApp message confirming this check-in will follow shortly.",
  reference: "Reference",
  received: "Received",
  startAgain: "Start again",
  tapToEnter: "Tap to enter",
  tapToEdit: "Tap to edit",
  decrease: (n) => `Decrease ${n}`,
  increase: (n) => `Increase ${n}`,
  typeValue: (n) => `Type a value for ${n}`,
  painHint: (min, max) => `${min} is no pain, ${max} is the worst you can imagine`,
  painLevels: ["No pain", "Mild", "Uncomfortable", "Moderate", "Severe", "Worst possible"],
  outOf: (s, m) => `${s} out of ${m}`,
};

const TA: CheckInText = {
  locale: "ta-IN",
  language: "மொழி",
  loading: "பதிவு ஏற்றப்படுகிறது…",
  openFromWhatsAppTitle: "WhatsApp-இலிருந்து உங்கள் பதிவைத் திறக்கவும்",
  openFromWhatsAppBody: "மருத்துவமனையின் WhatsApp நினைவூட்டலில் உள்ள இணைப்பிலிருந்து இன்றைய பதிவு திறக்கும்.",
  linkErrorTitle: "இந்த இணைப்பைத் திறக்க முடியவில்லை",
  linkErrorAdvice: "இது தொடர்ந்தால், உங்கள் சமீபத்திய WhatsApp நினைவூட்டலில் உள்ள இணைப்பைப் பயன்படுத்தவும்.",
  backendUnavailable: "சேவையகத்தை அணுக முடியவில்லை",
  greeting: "வணக்கம்,",
  dayAfterSurgery: (day) => `அறுவை சிகிச்சைக்குப் பின் ${day}-ஆம் நாள்`,
  alreadyCheckedIn: "இன்று நீங்கள் ஏற்கனவே பதிவு செய்துவிட்டீர்கள்",
  checkInReady: "இன்றைய பதிவு தயாராக உள்ளது",
  overview: (q, s, h) => `${s} படிகளில் ${q} கேள்விகள். ${h} மருத்துவக் குழு ஒவ்வொரு பதிலையும் பார்க்கும்.`,
  startCheckIn: "இன்றைய பதிவைத் தொடங்கவும்",
  checkInAgain: "மீண்டும் பதிவு செய்யவும்",
  goBack: "பின் செல்ல",
  stepOf: (step, of) => `படி ${step} / ${of}`,
  continue: "தொடரவும்",
  sendToCareTeam: "என் மருத்துவக் குழுவுக்கு அனுப்பவும்",
  sending: "அனுப்பப்படுகிறது…",
  answeredOf: (a, n) => `${n} கேள்விகளில் ${a} பதிலளிக்கப்பட்டன`,
  sections: { readings: "உங்கள் அளவீடுகள்", checks: "அறிகுறிச் சோதனைகள்", progress: "நடமாட்டம்" },
  checksIntro: "நேற்றிலிருந்து இவற்றில் ஏதேனும் கவனித்தீர்களா?",
  photoStep: "காயத்தின் புகைப்படம்",
  reviewStep: "சரிபார்த்து அனுப்பவும்",
  answerRequired: "சிவப்பில் குறிக்கப்பட்ட ஒவ்வொரு கேள்விக்கும் பதிலளிக்கவும்.",
  pleaseAnswer: "இந்தக் கேள்விக்குப் பதிலளிக்கவும்",
  skippedPrompt: (names) =>
    `நீங்கள் பதிலளிக்காதவை: ${names}. உங்கள் மருத்துவக் குழு இவற்றைப் "பதிலளிக்கவில்லை" எனக் காணும்.`,
  answerThem: "பதிலளிக்கிறேன்",
  continueWithout: "பதிலளிக்காமல் தொடரவும்",
  urgentTitle: "உடனே எங்களை அழைக்கவும்",
  urgentWithWard: (s, h) =>
    `நீங்கள் ${s} பற்றிக் கூறினீர்கள். இந்தப் பதிவு பார்க்கப்படும் வரை காத்திருக்க வேண்டாம்: இப்போதே ${h}-ஐ அழைக்கவும். தொடர்பு கிடைக்கவில்லை என்றால், அவசர சேவை எண் ${EMERGENCY_SERVICES}-ஐ அழைக்கவும்.`,
  urgentNoWard: (s) =>
    `நீங்கள் ${s} பற்றிக் கூறினீர்கள். இந்தப் பதிவு பார்க்கப்படும் வரை காத்திருக்க வேண்டாம்: இப்போதே உங்கள் மருத்துவமனையை அழைக்கவும். அவர்களைத் தொடர்பு கொள்ள முடியவில்லை என்றால், அவசர சேவை எண் ${EMERGENCY_SERVICES}-ஐ அழைக்கவும்.`,
  callWard: "வார்டை அழைக்கவும்",
  call112: `அவசர சேவையை அழைக்கவும் (${EMERGENCY_SERVICES})`,
  and: " மற்றும் ",
  photoHint: "நல்ல வெளிச்சத்தில், காயத்திலிருந்து சுமார் 30 செ.மீ. தூரத்தில் போனைப் பிடிக்கவும்.",
  photoAlt: "நீங்கள் தேர்ந்தெடுத்த காயத்தின் புகைப்படம்",
  remove: "நீக்கவும்",
  takePhoto: "புகைப்படம் எடுக்கவும்",
  orGallery: "அல்லது கேலரியிலிருந்து தேர்ந்தெடுக்கவும்",
  photoNotSent: "தற்போது புகைப்படம் இந்த போனிலேயே இருக்கும்; உங்கள் பதிவுடன் அனுப்பப்படாது.",
  couldNotSend: "அனுப்ப முடியவில்லை",
  edit: "மாற்றவும்",
  woundPhoto: "காயத்தின் புகைப்படம்",
  noPhoto: "புகைப்படம் சேர்க்கப்படவில்லை",
  notAnswered: "பதிலளிக்கவில்லை",
  yes: "ஆம்",
  no: "இல்லை",
  alreadySent: "ஏற்கனவே அனுப்பப்பட்டது",
  checkInSent: "பதிவு அனுப்பப்பட்டது",
  alreadySentBody: "இந்தப் பதிவு ஏற்கனவே எங்களுக்கு வந்துவிட்டது; எதுவும் இரட்டிப்பாகவில்லை.",
  answersRecorded: (n, d) =>
    n === 1 ? `${d}-ஆம் நாளுக்கு 1 பதில் பதிவு செய்யப்பட்டது.` : `${d}-ஆம் நாளுக்கு ${n} பதில்கள் பதிவு செய்யப்பட்டன.`,
  replacesEarlier: "இது இன்று நீங்கள் முன்பு அனுப்பிய பதிவுக்குப் பதிலாக அமையும்.",
  urgentDone:
    "இன்று கவனிக்க வேண்டிய ஒரு அறிகுறியைக் கூறியுள்ளீர்கள். வார்டுடன் இன்னும் பேசவில்லை என்றால், உடனே அழைக்கவும்.",
  whatsappSent: "இந்தப் பதிவை உறுதிசெய்யும் WhatsApp செய்தி உங்களுக்கு அனுப்பப்பட்டுள்ளது.",
  whatsappQueued: "இந்தப் பதிவை உறுதிசெய்யும் WhatsApp செய்தி விரைவில் வரும்.",
  reference: "குறிப்பு எண்",
  received: "பெறப்பட்டது",
  startAgain: "மீண்டும் தொடங்கவும்",
  tapToEnter: "உள்ளிட தட்டவும்",
  tapToEdit: "மாற்ற தட்டவும்",
  decrease: (n) => `${n} குறைக்க`,
  increase: (n) => `${n} அதிகரிக்க`,
  typeValue: (n) => `${n} மதிப்பைத் தட்டச்சு செய்ய`,
  painHint: (min, max) => `${min} என்றால் வலி இல்லை, ${max} என்றால் கற்பனை செய்யக்கூடிய மிக மோசமான வலி`,
  painLevels: ["வலி இல்லை", "லேசான வலி", "அசௌகரியம்", "மிதமான வலி", "கடுமையான வலி", "மிக மோசமான வலி"],
  outOf: (s, m) => `${m}-இல் ${s}`,
};

const HI: CheckInText = {
  locale: "hi-IN",
  language: "भाषा",
  loading: "चेक-इन लोड हो रहा है…",
  openFromWhatsAppTitle: "अपना चेक-इन WhatsApp से खोलें",
  openFromWhatsAppBody: "आज का चेक-इन अस्पताल के WhatsApp रिमाइंडर में दिए लिंक से खुलता है।",
  linkErrorTitle: "यह लिंक नहीं खुल सका",
  linkErrorAdvice: "अगर ऐसा बार-बार हो, तो अपने सबसे नए WhatsApp रिमाइंडर का लिंक इस्तेमाल करें।",
  backendUnavailable: "सर्वर उपलब्ध नहीं है",
  greeting: "नमस्ते,",
  dayAfterSurgery: (day) => `सर्जरी के बाद दिन ${day}`,
  alreadyCheckedIn: "आप आज पहले ही चेक-इन कर चुके हैं",
  checkInReady: "आज का चेक-इन तैयार है",
  overview: (q, s, h) => `${s} चरणों में ${q} सवाल। ${h} की देखभाल टीम हर जवाब देखती है।`,
  startCheckIn: "आज का चेक-इन शुरू करें",
  checkInAgain: "फिर से चेक-इन करें",
  goBack: "वापस जाएँ",
  stepOf: (step, of) => `चरण ${step} / ${of}`,
  continue: "आगे बढ़ें",
  sendToCareTeam: "मेरी देखभाल टीम को भेजें",
  sending: "भेजा जा रहा है…",
  answeredOf: (a, n) => `${n} में से ${a} सवालों के जवाब दिए गए`,
  sections: { readings: "आपकी रीडिंग", checks: "लक्षणों की जाँच", progress: "चलना-फिरना" },
  checksIntro: "कल से, क्या आपने इनमें से कुछ महसूस किया है?",
  photoStep: "घाव की फ़ोटो",
  reviewStep: "जाँचें और भेजें",
  answerRequired: "लाल रंग से चिह्नित हर सवाल का जवाब दें।",
  pleaseAnswer: "कृपया इस सवाल का जवाब दें",
  skippedPrompt: (names) =>
    `आपने इनका जवाब नहीं दिया: ${names}। आपकी देखभाल टीम इन्हें "जवाब नहीं दिया" के रूप में देखेगी।`,
  answerThem: "इनका जवाब दें",
  continueWithout: "बिना जवाब दिए आगे बढ़ें",
  urgentTitle: "कृपया हमें अभी फ़ोन करें",
  urgentWithWard: (s, h) =>
    `आपने ${s} के बारे में बताया है। इस चेक-इन की समीक्षा का इंतज़ार न करें: अभी ${h} को फ़ोन करें। अगर संपर्क न हो पाए, तो आपातकालीन सेवा ${EMERGENCY_SERVICES} पर फ़ोन करें।`,
  urgentNoWard: (s) =>
    `आपने ${s} के बारे में बताया है। इस चेक-इन की समीक्षा का इंतज़ार न करें: अभी अपने अस्पताल को फ़ोन करें। अगर उनसे संपर्क न हो पाए, तो आपातकालीन सेवा ${EMERGENCY_SERVICES} पर फ़ोन करें।`,
  callWard: "वार्ड को फ़ोन करें",
  call112: `आपातकालीन सेवा को फ़ोन करें (${EMERGENCY_SERVICES})`,
  and: " और ",
  photoHint: "अच्छी रोशनी में फ़ोन को घाव से लगभग 30 सेमी दूर रखें।",
  photoAlt: "आपकी चुनी हुई घाव की फ़ोटो",
  remove: "हटाएँ",
  takePhoto: "फ़ोटो लें",
  orGallery: "या अपनी गैलरी से चुनें",
  photoNotSent: "अभी यह फ़ोटो इसी फ़ोन पर रहती है; यह आपके चेक-इन के साथ नहीं भेजी जाती।",
  couldNotSend: "भेजा नहीं जा सका",
  edit: "बदलें",
  woundPhoto: "घाव की फ़ोटो",
  noPhoto: "कोई फ़ोटो नहीं जोड़ी गई",
  notAnswered: "जवाब नहीं दिया",
  yes: "हाँ",
  no: "नहीं",
  alreadySent: "पहले ही भेजा जा चुका है",
  checkInSent: "चेक-इन भेज दिया गया",
  alreadySentBody: "यह चेक-इन हमें पहले ही मिल चुका था, इसलिए कुछ भी दोहराया नहीं गया।",
  answersRecorded: (n, d) =>
    n === 1 ? `दिन ${d} के लिए 1 जवाब दर्ज किया गया।` : `दिन ${d} के लिए ${n} जवाब दर्ज किए गए।`,
  replacesEarlier: "यह आज पहले भेजे गए आपके चेक-इन की जगह लेता है।",
  urgentDone:
    "आपने ऐसे लक्षण के बारे में बताया है जिस पर आज ध्यान देना ज़रूरी है। अगर आपने अभी तक वार्ड से बात नहीं की है, तो कृपया अभी फ़ोन करें।",
  whatsappSent: "इस चेक-इन की पुष्टि करने वाला WhatsApp संदेश आपको भेज दिया गया है।",
  whatsappQueued: "इस चेक-इन की पुष्टि करने वाला WhatsApp संदेश जल्द ही आएगा।",
  reference: "संदर्भ संख्या",
  received: "प्राप्त हुआ",
  startAgain: "फिर से शुरू करें",
  tapToEnter: "दर्ज करने के लिए टैप करें",
  tapToEdit: "बदलने के लिए टैप करें",
  decrease: (n) => `${n} कम करें`,
  increase: (n) => `${n} बढ़ाएँ`,
  typeValue: (n) => `${n} का मान टाइप करें`,
  painHint: (min, max) => `${min} का मतलब कोई दर्द नहीं, ${max} का मतलब सबसे बुरा दर्द जिसकी आप कल्पना कर सकें`,
  painLevels: ["कोई दर्द नहीं", "हल्का", "असहज", "मध्यम", "तेज़", "सबसे बुरा"],
  outOf: (s, m) => `${m} में से ${s}`,
};

const TEXT: Record<CheckInLanguage, CheckInText> = { en: EN, ta: TA, hi: HI };

export function checkInText(language: string | null | undefined): CheckInText {
  return TEXT[(language ?? "en") as CheckInLanguage] ?? EN;
}
