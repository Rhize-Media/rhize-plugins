# E-E-A-T Implementation Guide

Practical implementation of Google's Experience, Expertise, Authoritativeness, and Trustworthiness framework.

## Experience Signals

**What to implement:**
- Author bios mentioning relevant experience ("10 years in SEO")
- Case studies with real data and results
- Screenshots, videos, and documentation of firsthand testing
- Customer testimonials and reviews
- "About the Author" sections on every article

**Schema implementation:**
```json
{
  "@type": "Person",
  "name": "Author Name",
  "jobTitle": "SEO Director",
  "worksFor": { "@type": "Organization", "name": "Company" },
  "description": "10+ years of experience in technical SEO and content strategy",
  "knowsAbout": ["SEO", "Content Marketing", "Technical SEO"],
  "sameAs": ["https://linkedin.com/in/author"]
}
```

## Expertise Signals

**What to implement:**
- Display author credentials and certifications
- Cite primary sources (studies, documentation, official data)
- Demonstrate depth with comprehensive coverage
- Use accurate technical terminology
- Show publication history in the field

**Content patterns:**
- Include data and statistics from authoritative sources
- Reference specific methodologies, frameworks, and standards
- Cover edge cases and exceptions (shows deep knowledge)
- Link to related in-depth content on your site

## Authoritativeness Signals

**What to implement:**
- Backlinks from respected industry sites
- Mentions in industry publications
- Speaking at conferences (mention in author bio)
- Consistent publishing cadence
- Awards, certifications, and recognitions

**Site-level signals:**
- About page with company history and mission
- Team page with individual bios
- Press/media page
- Industry partnerships and affiliations

## Trustworthiness Signals

**What to implement:**
- Clear authorship on all content
- Visible publish dates and update dates
- Contact information (phone, email, address)
- HTTPS everywhere
- Privacy policy and terms of service
- Clear corrections policy (if errors found, how you handle them)

**Technical requirements:**
- SSL certificate (HTTPS)
- HSTS header
- No mixed content
- Accessible contact page
- Physical address (for businesses)

## YMYL Considerations

"Your Money or Your Life" topics require extra rigor:

**Health content:**
- Reviewed by healthcare professionals (display reviewer name and credentials)
- Cite peer-reviewed studies
- Include medical disclaimers
- Link to official health organizations (WHO, NIH, CDC)

**Financial content:**
- Written or reviewed by certified financial professionals
- Include relevant disclaimers
- Cite official regulatory sources
- Display author's financial credentials

**Legal content:**
- Reviewed by licensed attorneys
- Include jurisdiction disclaimers
- Cite official legal sources
- Clear "this is not legal advice" disclaimers

## Implementation Checklist

- [ ] Author schema (Person) on all content pages
- [ ] Author bio page with credentials, experience, and sameAs links
- [ ] datePublished and dateModified on all content
- [ ] Visible byline on every article
- [ ] About page with Organization schema
- [ ] Contact page with clear contact information
- [ ] Privacy policy and terms of service pages
- [ ] HTTPS enforced sitewide
- [ ] Sources and citations linked in content
- [ ] Expert reviewer attribution (for YMYL content)
