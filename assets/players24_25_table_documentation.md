# Players24_25 Table Documentation

## Table Overview
This table manages all player registrations for the 2024-25 season. Each record represents one registered player and contains comprehensive information including:
- Personal and contact details
- Parent/guardian information
- Payment tracking for membership and monthly subscriptions
- Kit selections (sizes, types, and preferred shirt numbers)
- Photo ID submission status
- Consent records and agreements
- Record creation and modification timestamps

## Categories

### 1. Player Personal Information
#### playerFirstName1
- **Description**: Player's first name.
- **Boolean or Non-boolean**: Non-boolean
- **Common Values**: "George"
- **Format of Value**: Capitalized first letter
- **Field Type**: String

#### playerSurname1
- **Description**: Player's surname.
- **Boolean or Non-boolean**: Non-boolean
- **Common Values**: "Berry"
- **Format of Value**: Capitalized first letter
- **Field Type**: String

#### playerDOB1
- **Description**: Player's date of birth.
- **Boolean or Non-boolean**: Non-boolean
- **Common Values**: "31-07-2013"
- **Format of Value**: DD-MM-YYYY
- **Field Type**: String (date format)
- **Notes**: Use this field to calculate the age of a player if needed, as the current date should always be passed to you in the query.

#### playerGender1
- **Description**: Gender identification of the player.
- **Boolean or Non-boolean**: Non-boolean
- **Common Values**: "Male", "Female", "Gender Neutral", "Rather Not Say"
- **Format of Value**: Capitalized word
- **Field Type**: String

#### playerFullAdd1
- **Description**: Full address of the player, with the first address line, town (area), city, and postcode separated by commas.
- **Boolean or Non-boolean**: Non-boolean
- **Common Values**: "22 Elizabeth Rd, Partington, Manchester, M31 4PU"
- **Format of Value**: Comma-separated string
- **Field Type**: String (multi-line)

### 2. Player Team & Membership Information
#### playerTeam1
- **Description**: Specific team within the player's age group.
- **Boolean or Non-boolean**: Non-boolean
- **Common Values**: "Tigers", "Lions"
- **Format of Value**: Capitalized
- **Field Type**: String

#### playerAgeGroup1
- **Description**: Player's age group.
- **Boolean or Non-boolean**: Non-boolean
- **Common Values**: "u9s", "u13s"
- **Format of Value**: "uXs"
- **Field Type**: String
- **Notes**: Variations include "under 9s", "under nines", "u9".

#### playerMemberLastSeason
- **Description**: Status of player membership last season.
- **Boolean or Non-boolean**: Boolean
- **Exhaustive Values**: "Y", "N"
- **Format of Value**: Uppercase single character
- **Field Type**: String

#### playerID_2425
- **Description**: Unique identifier for the player record (auto-generated).
- **Boolean or Non-boolean**: Non-boolean
- **Common Values**: "rec3aGjf9bJdHxiHd"
- **Format of Value**: Alphanumeric string
- **Field Type**: String

### 3. Medical & Photo Information
#### playerKnownMedIssues1
- **Description**: Description of any declared medical issues.
- **Boolean or Non-boolean**: Non-boolean
- **Common Values**: "Asthma", "Peanut allergy"
- **Format of Value**: Sentence case
- **Field Type**: String

#### anyMedicalIssues
- **Description**: Indicates if medical issues exist (formula-based).
- **Boolean or Non-boolean**: Boolean
- **Exhaustive Values**: "Y", "N"
- **Field Type**: String

#### playerPhoto
- **Description**: Identifier tag in the URL of the player's uploaded photo ID.
- **Boolean or Non-boolean**: Non-boolean
- **Common Values**: "tigers_berry_george"
- **Format of Value**: Lowercase with underscores
- **Field Type**: String

#### photoReceived
- **Description**: Indicates if the player's photo has been received (formula-based).
- **Boolean or Non-boolean**: Boolean
- **Exhaustive Values**: "Y", "N"
- **Field Type**: String

### 4. Parent/Guardian Information
#### parGdnFirstName1
- **Description**: First name of the parent or guardian.
- **Boolean or Non-boolean**: Non-boolean
- **Common Values**: "Peter"
- **Format of Value**: Capitalized first letter
- **Field Type**: String

#### parGdnSurname1
- **Description**: Surname of the parent or guardian.
- **Boolean or Non-boolean**: Non-boolean
- **Common Values**: "Berry"
- **Field Type**: String

#### parGdnFullName1
- **Description**: Full name of the parent or guardian (formula).
- **Field Type**: String

#### parGdnDOB1
- **Description**: Date of birth of the parent or guardian.
- **Common Values**: "21-06-1984"
- **Format of Value**: DD-MM-YYYY
- **Field Type**: String (date format)

#### parGdnEmail1
- **Description**: Email address of the parent or guardian.
- **Format of Value**: Standard email format
- **Field Type**: String

#### parGdnTel1
- **Description**: Contact number of the parent or guardian.
- **Field Type**: String

#### parGdnFullAdd1
- **Description**: Full address of the parent or guardian.
- **Field Type**: String (multi-line)

#### parGdnRelToChild1
- **Description**: Relationship to the player.
- **Common Values**: "Father", "Mother", "Legal Guardian"
- **Field Type**: String

### 5. Kit Information
#### kitRequired
- **Description**: If a kit is required (formula-based).
- **Exhaustive Values**: "Y", "N"
- **Field Type**: String

#### kitType
- **Description**: Type of kit (Outfield or Goalkeeper).
- **Field Type**: String

#### kitSize
- **Description**: Size of the kit.
- **Common Values**: "XLY", "Medium"
- **Field Type**: String

#### shirtNumber
- **Description**: Requested shirt number.
- **Field Type**: Numeric

### 6. Consent & Code of Conduct
#### consentGiven
- **Description**: Comprehensive consent covering data, participation, medical, communications, media.
- **Field Type**: String

#### consentWhatsApp
- **Description**: Consent for WhatsApp communication.
- **Field Type**: String

#### codeOfConductRead
- **Description**: FA code of conduct read indicator.
- **Field Type**: String

### 7. Payment Information
#### membershipFeeAmount
- **Description**: Annual membership fee amount.
- **Common Values**: "£40.00"
- **Field Type**: String

#### membershipFeeDesc
- **Description**: Description of membership fee.
- **Field Type**: String

#### paid_membership_fee
- **Description**: Indicator if membership fee paid.
- **Field Type**: String

#### subscriptionFeeDesc
- **Description**: Description of subscription fee.
- **Field Type**: String

#### subscriptionPaymentDay
- **Description**: Preferred subscription payment date.
- **Field Type**: Numeric

#### subscriptionEndDate
- **Description**: End date of subscription period.
- **Field Type**: Date

#### SEP_PAID, OCT_PAID, ... [Monthly payment status fields]
- **Description**: Status for each month ("Y"/"N"/"N/A").
- **Field Type**: String

#### discountApplied
- **Description**: Discount amount applied (%).
- **Field Type**: String

#### discount
- **Description**: Indicates if discount applied (formula-based).
- **Field Type**: String

### 8. Payment System Fields (GoCardless)
#### customerID, mandate_id, billingRequestsID, payment_id, subscriptionID
- **Description**: Identifiers in GoCardless system.
- **Field Type**: String

#### multipleSubscriptions, subscriptionSetup, bacsPayer, mandateAuthorised, newLinkGen
- **Description**: Various indicators (formula-based).
- **Field Type**: String

### 9. System Fields
#### Created
- **Description**: Record creation timestamp.
- **Field Type**: DateTime (ISO 8601)
