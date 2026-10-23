# Research references

Checked on 21 October 2026. "Verified" means the page was opened or its content confirmed in this research; "lead" means it came from a team proposal and was not re-opened.

## Official and regulatory

| Source | Relevance | Status |
|---|---|---|
| [SIH 2026 problem statements (official portal)](https://sih.gov.in/sih2026PS) | Source of record for SIH26261 | Portal page could not be fetched from the build workspace; confirm the PS there |
| SIH 2026 idea-submission template (copies circulated by institutions, e.g. [this template copy](https://docs.google.com/presentation/d/1dX2CJZQPogJOWfnsCISr52fw4k75QnqK/htmlpresent)) | Six-slide structure: title, idea, technical approach, feasibility and viability, impact and benefits, research and references | Verified across several 2026 copies; not an official URL |
| [AICTE Approval Process Handbook 2024-27](https://aicte.gov.in/sites/default/files/APH%20Final.pdf) | Source for every rule; clauses still to be verified | Located; full text not read |
| [AICTE notice on the 2026-27 approval process (hosted by BTEUP)](https://bteup.ac.in/PDFFILES/NEWS_639005651817728160.pdf) | APH 2024-25 to 2026-27 applies; portal opened 28 Nov 2025 | Verified |
| [Sample AICTE EoA letter 2026-27 (CUSAT)](https://soe.cusat.ac.in/assets/files/aicte_eoa_letters/EOA_Report_2026-2027.pdf) | Field structure for synthetic templates; instructions that council records prevail and that course details be verified on the AICTE website; reference to APH Chapter VI norms | Verified (structure only; nothing copied) |
| [DigiLocker onboarding FAQ](https://www.digilocker.gov.in/assets/FAQ%20DL%20EL_onboarding.pdf) | Requesters register on API Setu; holder consent via OAuth; issuers onboard separately | Verified |
| [API Setu](https://api.apisetu.gov.in) | Registration point for requester access | Lead |
| [Controller of Certifying Authorities — digital signatures](https://cca.gov.in/digital_signature.html) | Legal framework and trust roots for verifying digital signatures | Located |
| [Digital Personal Data Protection Act 2023 (Digital India)](https://digitalindia.gov.in/dpdp) | Privacy obligations for institutional and personal data | Located |

## Academic research

| Source | Relevance | Status |
|---|---|---|
| [Qu et al., *Towards Robust Tampered Text Detection in Document Image*, CVPR 2023 (DocTamper)](https://openaccess.thecvf.com/content/CVPR2023/html/Qu_Towards_Robust_Tampered_Text_Detection_in_Document_Image_New_Dataset_CVPR_2023_paper.html), [code](https://github.com/qcf-568/DocTamper) | Main tampered-text benchmark. Its README restricts the dataset to non-commercial use by university or research staff, so it is not used here | Verified |
| [Wong et al., *ADCD-Net*, ICCV 2025](https://openaccess.thecvf.com/content/ICCV2025/papers/Wong_ADCD-Net_Robust_Document_Image_Forgery_Localization_via_Adaptive_DCT_Feature_ICCV_2025_paper.pdf) ([arXiv 2507.16397](https://arxiv.org/abs/2507.16397)) | Recent forgery localization; candidate optional signal | Verified (listing) |
| [Wu et al., *AIForge-Doc*, arXiv 2602.20569 (Feb 2026)](https://arxiv.org/abs/2602.20569) | 4,061 AI-forged document images; DocTamper's detector falls from 0.98 AUC in-distribution to 0.563, and a zero-shot GPT-4o judge scores 0.509. Motivates source verification and abstention over pixel forensics | Verified (abstract) |
| [Angelopoulos & Bates, *A Gentle Introduction to Conformal Prediction*](https://arxiv.org/abs/2107.07511) | Basis for calibrated abstention once real calibration data exist | Verified (listing) |

## Implementation references
[pdfplumber](https://github.com/jsvine/pdfplumber) · [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) · [pikepdf](https://pikepdf.readthedocs.io/) · [Tesseract OCR](https://tesseract-ocr.github.io/tessdoc/) · [pyHanko (planned)](https://pyhanko.readthedocs.io/) · [Starlette](https://www.starlette.io/) · [Pydantic](https://docs.pydantic.dev/) · [React](https://react.dev/) · [Tailwind CSS](https://tailwindcss.com/docs) · [esbuild](https://esbuild.github.io/) · [OWASP ASVS](https://owasp.org/ASVS/)

## Prior art

| Project | What its README describes | How PRAMAAN differs | Status |
|---|---|---|---|
| [AICTE Document Verification — Team ARTH](https://github.com/theparthgupta/aicte_doc_verification) | SIH 2024 winner (self-reported); multi-role portal, OCR, template comparison, fraud detection, chatbot, audit logging; claims "90%+ accuracy" without method | No rule versioning, abstention or issuer verification described. PRAMAAN does not claim novelty for AICTE document workflows in general | Verified (README) |
| [AICTE Portal Automation](https://github.com/AyonSOMADDAR/AICTE_Portal_Automation) | OCR extraction, summaries, discrepancy reports | Treated as baseline capability | Lead |
| [Sentinel-AI](https://github.com/sanashk19/Sentinel-AI) | Multi-signal tamper score for ID documents | Single-document score vs bundle-level, rule-grounded findings | Lead (team proposal opened it) |

## Third-party commentary (context only)
- [SIH 2026 software PS archive, first lot (unofficial)](https://github.com/Rugved-dev18/SIH-2026-official-Software-Problem-Statements) — 172 statements up to SIH26209; used only to check numbering.
- [SIH 2026 PS snapshot of 22 Aug 2026 (unofficial)](https://github.com/NoBugNinja/Smart-India-Hackathon-SIH-2026-Problem-Statements) — up to SIH26226; SIH26261 not present, so it was presumably released later.
- [Careers360 on the APH 2024-27 launch](https://news.careers360.com/aicte-launch-approval-process-handbook-for-2024-27-academic-session-on-december-6/amp) — context on the handbook cycle.
