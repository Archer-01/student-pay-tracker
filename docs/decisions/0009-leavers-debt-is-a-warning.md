# 0009. A leaver's debt is a warning, never a block

- Status: Accepted
- Decided: sprint 13, with the teacher · Recorded: 2026-11-21

## Context
The first notes asked for a "blacklist": students who left owing should have to pay before they
can come back. Asked how it works in practice, the teacher said they check the app themselves
and ask the student to pay what they owe, or leave.

## Decision
The app makes the debt impossible to miss, and never enforces anything. Former students who
left owing are listed in Bilan › Partis sans régler and on Accueil; marking someone as returned
shows what they owe and lets the teacher go on; enrolling someone whose phone or name matches a
leaver who owes shows a warning (`services/debt_service.py`). Paying the months clears it; the
teacher can also stop chasing it (« Ne plus réclamer »), a write-off that is never a payment.

## Rejected
- **Refusing a return or an enrolment while a debt is open**: the decision is the teacher's, and
  real people share names; a block would also need a record of who lifted it.
- **Recording a fake payment to clear the list**: it would inflate the money collected and the
  school's share. The write-off exists so nobody needs to.
- **Calling it a blacklist**: it implies an enforcement the app deliberately doesn't do.

## Consequences
- A returning student with debt is the teacher's call, every time; don't add checks that refuse
  it.
