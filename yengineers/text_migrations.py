"""Textes par défaut remplacés lors du passage à la tranche d'âge 7-18 ans.

Appliqués seulement si le texte en base est encore EXACTEMENT l'ancien texte par défaut
(jamais si l'administrateur l'a modifié).
"""

TEXT_MIGRATIONS = {
    "settings": [
        ('about_text_ar', 'Young Engineers نادٍ للروبوتيك والتكنولوجيا في قابس، موجّه للشباب من 13 إلى 18 سنة الراغبين في اكتشاف التكنولوجيا والتعلّم بالممارسة وتنمية إبداعهم.', 'Young Engineers نادٍ للروبوتيك والتكنولوجيا في قابس، موجّه للشباب من 7 إلى 18 سنة الراغبين في اكتشاف التكنولوجيا والتعلّم بالممارسة وتنمية إبداعهم.'),
        ('about_text_fr', 'Young Engineers est un club de robotique et de technologie à Gabès, destiné aux jeunes de 13 à 18 ans qui souhaitent découvrir la technologie, apprendre en pratiquant et développer leur créativité.', 'Young Engineers est un club de robotique et de technologie à Gabès, destiné aux jeunes de 7 à 18 ans qui souhaitent découvrir la technologie, apprendre en pratiquant et développer leur créativité.'),
        ('about_text_en', 'Young Engineers is a robotics and technology club in Gabès for young people aged 13 to 18 who want to discover technology, learn by doing and grow their creativity.', 'Young Engineers is a robotics and technology club in Gabès for young people aged 7 to 18 who want to discover technology, learn by doing and grow their creativity.'),
    ],
    "faqs": [
        ('answer_ar', 'يتوجّه نادي Young Engineers إلى الشباب من 13 إلى 18 سنة الراغبين في اكتشاف التكنولوجيا والتعلّم بالممارسة وتنمية إبداعهم.', 'يتوجّه نادي Young Engineers إلى الشباب من 7 إلى 18 سنة الراغبين في اكتشاف التكنولوجيا والتعلّم بالممارسة وتنمية إبداعهم.'),
        ('answer_ar', 'النادي موجّه للمراهقين من 13 إلى 18 سنة.', 'يستقبل النادي الأطفال والمراهقين من 7 إلى 18 سنة، في مجموعتين: 7–11 سنة و12–18 سنة.'),
        ('answer_fr', "Young Engineers s'adresse aux jeunes de 13 à 18 ans qui souhaitent découvrir la technologie, apprendre en pratiquant et développer leur créativité.", "Young Engineers s'adresse aux jeunes de 7 à 18 ans qui souhaitent découvrir la technologie, apprendre en pratiquant et développer leur créativité."),
        ('answer_fr', 'Le club est destiné aux adolescents de 13 à 18 ans.', 'Le club accueille les enfants et adolescents de 7 à 18 ans, en deux groupes : 7–11 ans et 12–18 ans.'),
        ('answer_en', 'Young Engineers is for young people aged 13 to 18 who want to discover technology, learn by doing and grow their creativity.', 'Young Engineers is for young people aged 7 to 18 who want to discover technology, learn by doing and grow their creativity.'),
        ('answer_en', 'The club is for teenagers aged 13 to 18.', 'The club welcomes children and teenagers aged 7 to 18, in two groups: 7–11 and 12–18.'),
    ],
}
