# Privacy Policy — Sports Narrator Alexa Skill

**Last updated:** February 2026

This Privacy Policy describes how Machina Sports ("we", "us", or "our") collects, uses, and stores information when you use the **Sports Narrator** Alexa skill ("the Skill").

---

## 1. Information We Collect

When you use the Skill, we collect and store the following information:

| Data | Purpose | Retention |
|------|---------|-----------|
| **Alexa User ID** | Uniquely identify your profile across sessions | Until you delete your data |
| **Favorite teams** | Personalize your sports updates and game reminders | Until you remove them or delete your data |

We do **not** collect your name, email address, payment information, or any other personally identifiable information beyond the anonymized Alexa User ID provided by Amazon.

---

## 2. How We Use Your Information

Your data is used exclusively to:

- **Personalize sports updates** — show results only for your saved favorite teams
- **Set game reminders** — identify your next upcoming match and schedule an Alexa Reminder
- **Improve the Skill** — aggregate, anonymized usage logs help us improve performance

We do **not** sell, rent, or share your personal data with third parties for marketing purposes.

---

## 3. Third-Party Services

The Skill integrates with the following third-party services to provide sports data:

- **Sportradar** — provides real-time sports data (NFL, NBA, Soccer). Data is fetched on-demand and not stored beyond the response. [Sportradar Privacy Policy](https://sports-skills.sh/)
- **Machina AI** — our own platform processes your requests and stores your favorite team preferences. Data is stored in a secure, encrypted database (MongoDB Atlas).
- **Amazon Alexa Reminders API** — used to set reminders on your Alexa device. Reminder content is provided by the Skill but stored and managed by Amazon.

---

## 4. Data Storage and Security

- All data is stored on **AWS infrastructure** in encrypted databases
- Access is restricted to authorized Machina personnel only
- We use HTTPS/TLS for all data in transit
- Your Alexa User ID is an opaque identifier — we cannot map it to your real identity

---

## 5. Your Rights

You may request deletion of your stored data at any time by:

1. Disabling the Skill in the Alexa app (this stops future data collection)
2. Emailing **privacy@machina.gg** with subject "Delete my Alexa Sports Narrator data"

We will process deletion requests within 30 days.

---

## 6. Children's Privacy

The Skill is not directed at children under 13 years of age. We do not knowingly collect personal information from children.

---

## 7. Changes to This Policy

We may update this Privacy Policy from time to time. We will notify users of significant changes by updating the "Last updated" date above.

---

## 8. Contact

For privacy-related questions or data deletion requests:

**Machina Sports**
Email: privacy@machina.gg
Website: https://machina.gg

---

> **Note for deployment:** This document must be hosted at a publicly accessible HTTPS URL and linked in the Alexa Developer Console under **Distribution > Privacy & Compliance**. Suggested URL: `https://machina.gg/privacy/alexa-sports-narrator`
