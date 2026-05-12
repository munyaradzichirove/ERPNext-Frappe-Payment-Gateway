````markdown
# 💳 Payment Gateway (Paynow + EcoCash) – Frappe App

A modular payment gateway system for ERPNext/Frappe supporting:

- 💵 Paynow (USD payments)
- 🇿🇼 EcoCash / ZWG mobile money
- 🧾 Payment Entry integration
- 🧪 Test mode simulation (Paynow sandbox logic)
- 🔴 Live production payments

---

# 🚀 Features

## 💳 Payment Processing

- Create payments from Sales Invoice
- Auto-generate Payment Entry
- Support for USD and ZWG flows

## 🧪 Test Mode Support

- Paynow sandbox integration mode
- Simulated responses using:
  - Test EcoCash numbers
  - Test tokens
- No real money movement

## 🔴 Live Mode

- Real Paynow + EcoCash integrations
- Webhook confirmation handling
- Production-ready transaction flow

## 🔁 Webhook Handling

- Automatic payment status updates
- Invoice reconciliation
- Failed / pending / success tracking

---

# 🧱 Architecture

```text
Payment Gateway App
│
├── Settings
│   ├── Paynow USD Settings
│   ├── EcoCash ZWG Settings
│   └── System Mode (Test / Live)
│
├── API Layer
│   ├── Paynow Service
│   ├── EcoCash Service
│   └── Payment Router
│
├── UI Layer
│   ├── Invoice Payment Buttons
│   └── Frappe Dialogs
│
└── Core Logic
    ├── Payment Entry Creation
    ├── Webhook Processor
    └── Status Updater
````

---

# ⚙️ Payment Flow

## 💵 USD (Paynow)

```text
Invoice → Button Click → Dialog → Backend API → Paynow → Webhook → Payment Entry → Invoice Paid
```

## 🇿🇼 ZWG (EcoCash)

```text
Invoice → Button Click → Dialog → Backend API → EcoCash → Callback → Payment Entry → Invoice Paid
```

---

# 🧪 Test Mode (Paynow)

When system is in TEST mode:

## Mobile Money Test Numbers

| Scenario           | Number     |
| ------------------ | ---------- |
| Success            | 0771111111 |
| Delayed Success    | 0772222222 |
| Cancelled          | 0773333333 |
| Insufficient Funds | 0774444444 |

## Card / Token Testing

* Success token
* Pending token
* Failed token

No real money is processed in test mode.

---

# 🔐 Settings Structure

## 🌐 System Mode

* Test
* Live

## 💵 Paynow USD Settings

* Integration ID (Test & Live)
* Integration Key (Test & Live)
* Enabled

## 🇿🇼 EcoCash Settings

* API Key (Test & Live)
* API Secret (Test & Live)
* Shortcode
* Enabled

---

# 🧠 Design Principles

* No sandbox/live UI buttons
* No per-transaction environment switching
* No mixing currencies in same flow
* System-wide mode control
* Backend-controlled payment logic
* UI only triggers payment actions
* Full audit trail through Payment Entry

---

# 🖥️ UI Behavior

* Single payment button per invoice

  * Pay with Paynow (USD)
  * Pay with EcoCash (ZWG)

* System automatically:

  * chooses correct gateway
  * uses correct credentials
  * handles test/live behavior

---

# 🔥 Security Features

* Prevents accidental live payments in test mode
* Webhook validation
* Duplicate payment protection
* Invoice state validation

---

# 🛠️ Tech Stack

* Frappe Framework
* ERPNext
* Paynow API
* EcoCash API
* Python
* JavaScript

---

# 🚀 Future Improvements

* Multi-gateway routing
* OneMoney / InnBucks support
* Payment retry system
* Real-time payment dashboard
* Mobile app support

---

# 📌 Summary

This system provides a clean separation of concerns:

> UI triggers payments
> Backend processes logic
> Payment gateways move money
> Webhooks reconcile transactions

```
```
