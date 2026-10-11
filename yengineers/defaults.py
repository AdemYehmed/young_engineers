"""Contenu éditorial initial (modifiable ensuite depuis /admin).

Aucune donnée inventée : pas de tarif, pas de date d'ouverture, pas d'adresse précise,
pas de témoignage, pas de certification, pas d'inscrit.
"""

DEFAULT_SETTINGS = {
    # Identité et coordonnées
    "club_name": "Young Engineers",
    "email": "youngengineers.gabes@gmail.com",
    "phone": "+216 25 676 360",
    "location_ar": "قابس، تونس",
    "location_fr": "Gabès, Tunisie",
    "location_en": "Gabès, Tunisia",
    "logo_file": "",
    # Réseaux sociaux (vides = non affichés)
    "social_facebook": "",
    "social_instagram": "",
    "social_youtube": "",
    "social_tiktok": "",
    "social_linkedin": "",
    # Section principale
    "hero_title_ar": "اكتشف عالم الروبوتيك والتكنولوجيا في قابس!",
    "hero_title_fr": "Découvrez le monde de la robotique et de la technologie à Gabès !",
    "hero_title_en": "Discover the world of robotics and technology in Gabès!",
    "hero_subtitle_ar": "خلّي صغيرك يكتشف البرمجة، الإلكترونيات والروبوتيك من خلال مشاريع تطبيقية تنمّي الإبداع والتفكير.",
    "hero_subtitle_fr": "Laissez votre adolescent(e) découvrir la programmation, l'électronique et la robotique à travers des projets pratiques qui développent la créativité et la réflexion.",
    "hero_subtitle_en": "Let your teen discover programming, electronics and robotics through hands-on projects that build creativity and critical thinking.",
    "hero_cta_primary_ar": "سجّل اهتمامك الآن",
    "hero_cta_primary_fr": "Je manifeste mon intérêt",
    "hero_cta_primary_en": "Register your interest now",
    "hero_cta_secondary_ar": "اكتشف أنشطتنا",
    "hero_cta_secondary_fr": "Découvrir nos activités",
    "hero_cta_secondary_en": "Discover our activities",
    "launch_notice_ar": "موعد انطلاق النادي لم يُحدَّد بعد، وسيُعلن عنه حسب عدد التسجيلات المسبقة.",
    "launch_notice_fr": "La date de lancement n'est pas encore fixée : elle dépendra du nombre de préinscriptions reçues.",
    "launch_notice_en": "The launch date is not set yet: it will depend on the number of pre-registrations received.",
    # Présentation
    "about_title_ar": "نادي للشباب المولعين بالتكنولوجيا",
    "about_title_fr": "Un club pour les jeunes passionnés de technologie",
    "about_title_en": "A club for young technology enthusiasts",
    "about_text_ar": "Young Engineers نادٍ للروبوتيك والتكنولوجيا في قابس، موجّه للشباب من 13 إلى 18 سنة الراغبين في اكتشاف التكنولوجيا والتعلّم بالممارسة وتنمية إبداعهم.",
    "about_text_fr": "Young Engineers est un club de robotique et de technologie à Gabès, destiné aux jeunes de 13 à 18 ans qui souhaitent découvrir la technologie, apprendre en pratiquant et développer leur créativité.",
    "about_text_en": "Young Engineers is a robotics and technology club in Gabès for young people aged 13 to 18 who want to discover technology, learn by doing and grow their creativity.",
    # Préinscription
    "prereg_title_ar": "عبّروا عن اهتمامكم منذ الآن",
    "prereg_title_fr": "Manifestez votre intérêt dès maintenant",
    "prereg_title_en": "Express your interest today",
    "prereg_text_ar": "يمكن للشباب وأوليائهم التعبير عن اهتمامهم منذ الآن. سيتم الإعلان عن انطلاق النادي عند بلوغ العدد اللازم من التسجيلات المسبقة. التسجيل النهائي لم يُفتح بعد.",
    "prereg_text_fr": "Les jeunes et leurs parents peuvent manifester leur intérêt dès maintenant. Le lancement du club sera annoncé lorsque le nombre nécessaire de préinscriptions sera atteint. Les inscriptions définitives ne sont pas encore ouvertes.",
    "prereg_text_en": "Young people and their parents can express their interest right now. The club's launch will be announced once the required number of pre-registrations is reached. Final enrolment is not open yet.",
    # Pages légales
    "data_retention_months": "12",
    "legal_extra_ar": "",
    "legal_extra_fr": "",
    "legal_extra_en": "",
}

DEFAULT_ACTIVITIES = [
    {
        "icon": "robot",
        "title_ar": "الروبوتيك", "title_fr": "Robotique", "title_en": "Robotics",
        "description_ar": "اكتشاف الروبوتات ومكوّناتها وكيفية عملها.",
        "description_fr": "Découvrir les robots et leurs composants.",
        "description_en": "Discover robots and the components they are made of.",
    },
    {
        "icon": "code",
        "title_ar": "البرمجة", "title_fr": "Programmation", "title_en": "Programming",
        "description_ar": "تعلّم كتابة الأكواد وتطوير التفكير المنطقي والبرمجي.",
        "description_fr": "Apprendre à écrire du code et développer une logique informatique.",
        "description_en": "Learn to write code and build computational thinking.",
    },
    {
        "icon": "chip",
        "title_ar": "الإلكترونيات", "title_fr": "Électronique", "title_en": "Electronics",
        "description_ar": "التعرّف على الدارات والمستشعرات والمكوّنات الإلكترونية.",
        "description_fr": "Découvrir les circuits, les capteurs et les composants.",
        "description_en": "Explore circuits, sensors and electronic components.",
    },
    {
        "icon": "wrench",
        "title_ar": "المشاريع التطبيقية", "title_fr": "Projets pratiques", "title_en": "Hands-on projects",
        "description_ar": "تصميم وإنجاز مشاريع تكنولوجية تطبيقية.",
        "description_fr": "Concevoir et réaliser des projets technologiques.",
        "description_en": "Design and build technology projects.",
    },
    {
        "icon": "bulb",
        "title_ar": "الابتكار", "title_fr": "Innovation", "title_en": "Innovation",
        "description_ar": "تحويل فكرة إلى نموذج أولي.",
        "description_fr": "Transformer une idée en prototype.",
        "description_en": "Turn an idea into a prototype.",
    },
]

DEFAULT_FAQS = [
    {
        "question_ar": "لمن يتوجّه النادي؟",
        "question_fr": "À qui s'adresse le club ?",
        "question_en": "Who is the club for?",
        "answer_ar": "يتوجّه نادي Young Engineers إلى الشباب من 13 إلى 18 سنة الراغبين في اكتشاف التكنولوجيا والتعلّم بالممارسة وتنمية إبداعهم.",
        "answer_fr": "Young Engineers s'adresse aux jeunes de 13 à 18 ans qui souhaitent découvrir la technologie, apprendre en pratiquant et développer leur créativité.",
        "answer_en": "Young Engineers is for young people aged 13 to 18 who want to discover technology, learn by doing and grow their creativity.",
    },
    {
        "question_ar": "ما هو السن المطلوب؟",
        "question_fr": "Quel âge faut-il avoir ?",
        "question_en": "What age do you need to be?",
        "answer_ar": "النادي موجّه للمراهقين من 13 إلى 18 سنة.",
        "answer_fr": "Le club est destiné aux adolescents de 13 à 18 ans.",
        "answer_en": "The club is for teenagers aged 13 to 18.",
    },
    {
        "question_ar": "هل يجب أن أعرف البرمجة مسبقًا؟",
        "question_fr": "Faut-il déjà connaître la programmation ?",
        "question_en": "Do I need to know programming already?",
        "answer_ar": "النادي مفتوح للمبتدئين أيضًا: تتيح استمارة التسجيل المسبق الإشارة إلى المستوى (مبتدئ أو متوسط أو متقدّم).",
        "answer_fr": "Le club s'adresse aussi aux débutants : le formulaire de préinscription permet d'indiquer son niveau (débutant, intermédiaire ou avancé).",
        "answer_en": "Beginners are welcome too: the pre-registration form lets you indicate your level (beginner, intermediate or advanced).",
    },
    {
        "question_ar": "أين يوجد النادي؟",
        "question_fr": "Où se trouve le club ?",
        "question_en": "Where is the club located?",
        "answer_ar": "النادي في قابس، تونس. سيتم الإعلان عن العنوان الدقيق لاحقًا.",
        "answer_fr": "Le club est situé à Gabès, en Tunisie. L'adresse précise sera communiquée ultérieurement.",
        "answer_en": "The club is in Gabès, Tunisia. The exact address will be announced later.",
    },
    {
        "question_ar": "متى ستنطلق الأنشطة؟",
        "question_fr": "Quand les activités commenceront-elles ?",
        "question_en": "When will the activities start?",
        "answer_ar": "موعد الانطلاق لم يُحدَّد بعد، وسيُعلن عنه لاحقًا حسب عدد التسجيلات المسبقة المتوصَّل بها.",
        "answer_fr": "La date de démarrage n'est pas encore fixée. Elle sera annoncée ultérieurement, en fonction du nombre de préinscriptions reçues.",
        "answer_en": "The start date is not set yet. It will be announced later, depending on the number of pre-registrations received.",
    },
    {
        "question_ar": "كيف أطلب معلومات إضافية؟",
        "question_fr": "Comment demander des informations ?",
        "question_en": "How can I ask for information?",
        "answer_ar": "راسلونا على youngengineers.gabes@gmail.com أو اتصلوا بنا على الرقم +216 25 676 360.",
        "answer_fr": "Écrivez-nous à youngengineers.gabes@gmail.com ou appelez-nous au +216 25 676 360.",
        "answer_en": "Email us at youngengineers.gabes@gmail.com or call +216 25 676 360.",
    },
]
