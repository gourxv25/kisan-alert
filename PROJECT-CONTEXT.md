# PROJECT_CONTEXT.md

# Kisan Alert

AI-powered multilingual agricultural advisory platform that helps farmers receive crop recommendations, disease diagnosis, weather alerts, and soil-based recommendations using Google Cloud services and Gemini AI.

---

# Project Goal

Build a production-inspired MVP for a hackathon.

The application should:

- Help farmers improve crop yield
- Detect crop diseases
- Recommend suitable crops
- Send weather alerts
- Work in regional languages
- Support low-literacy farmers
- Require NO custom ML model training

Gemini acts as the primary reasoning engine.

---

# Target Users

Primary Users

- Farmers
- Village coordinators
- Agricultural officers (RSK Officers)

Secondary Users

- Government departments
- NGOs
- Agricultural organizations

---

# Core Features

## 1. Farmer Registration

Farmer provides:

- Name
- Phone Number
- Village
- District
- State
- Preferred Language
- Farm GPS Location
- Plot Size
- Optional Soil Health Card ID

Store inside Firestore.

---

## 2. Crop Recommendation

Inputs

- Soil Data
- Weather Forecast
- NDVI
- Season
- Farmer Location

Gemini returns

- Best crops
- Reason
- Water requirement
- Sowing window

Output must support

- English
- Hindi
- Telugu
- Future regional languages

---

## 3. Crop Disease Diagnosis

Farmer uploads

- Crop image

Gemini Vision analyses

Returns

- Disease
- Pest
- Nutrient deficiency
- Confidence
- Immediate action

Officer reviews before final response.

---

## 4. Weather Alerts

Automatically monitor

- Rainfall
- Temperature
- Dry spell
- Heat stress

Notify farmers through

- SMS
- WhatsApp

---

## 5. Satellite Monitoring

Use NDVI

Monitor

- Crop health
- Vegetation changes
- Stress

Data Sources

Google Earth Engine

or

Agromonitoring API

---

## 6. Soil Health

Use

- Soil Health Card
- District soil defaults
- Village averages

Store

N

P

K

pH

Organic Carbon

---

## 7. Officer Dashboard

Dashboard should allow

View

- Farmers
- Alerts
- Disease Reports
- Crop Recommendations

Approve

Reject

Modify

AI responses before sending.

---

# High-Level Architecture

Farmer

↓

Cloud Function / Cloud Run API

↓

Firestore

↓

Gemini API

↓

Weather API

↓

Satellite API

↓

Officer Dashboard

↓

SMS / WhatsApp

↓

Farmer

---

# Recommended Tech Stack

Frontend

- React
- TypeScript
- TailwindCSS
- Vite

Backend

- FastAPI

Database

- Firebase Firestore

Authentication

- Firebase Authentication

Hosting

- Google Cloud Run

Background Jobs

- Google Cloud Scheduler

AI

- Gemini 2.5 Flash

Vision

- Gemini Vision

Maps

- Google Maps API

Satellite

- Google Earth Engine
- Agromonitoring API

Messaging

- Twilio WhatsApp Sandbox
- MSG91
- Gupshup

Weather

- OpenWeather API

Storage

- Firebase Storage

---

# Project Structure

backend/

    app/

        api/

        services/

        repositories/

        models/

        schemas/

        utils/

        config/

        prompts/

frontend/

    src/

        components/

        pages/

        hooks/

        services/

        types/

firebase/

docs/

scripts/

README.md

PROJECT_CONTEXT.md

---

# Firestore Collections

farmers

```json
{
  "name":"",
  "phone":"",
  "language":"",
  "village":"",
  "district":"",
  "state":"",
  "location":{
      "lat":0,
      "lng":0
  },
  "soil_ref":"",
  "created_at":""
}
```

plots

```json
{
 "farmer_id":"",
 "location":{},
 "ndvi_history":[],
 "soil_data":{},
 "weather_cache":{}
}
```

recommendations

```json
{
 "plot_id":"",
 "recommendation":{},
 "created_at":""
}
```

diagnosis

```json
{
 "photo_url":"",
 "diagnosis":"",
 "confidence":0,
 "status":"pending_review"
}
```

alerts

```json
{
 "farmer_id":"",
 "type":"",
 "message":"",
 "status":"",
 "created_at":""
}
```

---

# Backend Responsibilities

FastAPI should expose APIs for

Authentication

Farmer CRUD

Plot CRUD

Crop Recommendation

Disease Diagnosis

Weather Alerts

Officer Dashboard

Notification Service

Health Check

---

# AI Responsibilities

Gemini should perform

Crop recommendation

Disease diagnosis

Translation

Explanation generation

SMS generation

JSON generation

Never train custom models.

Use prompt engineering.

---

# Prompt Engineering Rules

Always request structured JSON.

Never request markdown.

Always specify

Language

Output Length

JSON schema

Example

```text
Respond ONLY in valid JSON.

{
 "crop":"",
 "reason":"",
 "water_need":"",
 "sowing_window":""
}
```

---

# Dashboard Features

Officer Login

Pending Reviews

Approve AI Result

Modify Result

Send to Farmer

Dashboard statistics

Realtime updates

---

# Background Jobs

Scheduler every 6 hours

Tasks

Fetch weather

Update NDVI

Generate alerts

Send SMS

Store history

---

# Notification Flow

Weather API

↓

Backend

↓

Gemini Summary

↓

Firestore

↓

Officer Approval

↓

Twilio / MSG91

↓

Farmer

---

# Coding Standards

Backend

- Python
- FastAPI
- Async endpoints
- Pydantic
- Repository pattern
- Service layer
- Dependency Injection

Frontend

- Functional Components
- React Hooks
- TypeScript
- Component-first design

Database

Never hardcode IDs.

Always use Firestore references.

---

# Error Handling

Every endpoint returns

```json
{
 "success":true,
 "message":"",
 "data":{}
}
```

Errors

```json
{
 "success":false,
 "error":"",
 "details":""
}
```

---

# Security

Never expose API Keys

Use environment variables

Validate every request

Sanitize AI inputs

Rate limit public APIs

Use Firebase Authentication

---

# MVP Priority

Priority 1

✅ Farmer Registration

Priority 2

✅ Crop Recommendation

Priority 3

✅ Disease Diagnosis

Priority 4

✅ Officer Dashboard

Priority 5

✅ Weather Alerts

Priority 6

✅ Satellite Monitoring

Priority 7

✅ Voice Support

---

# Future Roadmap

Offline mode

IVR Support

Voice Chat

Community Leader Mode

BigQuery Analytics

IoT Sensor Integration

Drone Integration

Yield Prediction

Market Price Prediction

Insurance Recommendation

Government Scheme Recommendation

---

# Development Principles

- Build modular services.
- Keep AI prompts separated from business logic.
- Prefer reusable APIs.
- Every AI response should be explainable.
- Keep APIs RESTful.
- Design for multilingual support from the beginning.
- Optimize for hackathon speed while maintaining production-quality architecture.
- Avoid custom ML training unless absolutely required.

---

# Success Criteria

The MVP should demonstrate:

✓ Farmer registration

✓ AI crop recommendation

✓ AI disease diagnosis

✓ Weather-based alerts

✓ Officer approval workflow

✓ Multilingual responses

✓ Firestore integration

✓ Google Cloud deployment

✓ End-to-end working demo

The system should rely primarily on Gemini AI, Firebase, and Google Cloud managed services to minimize infrastructure complexity while remaining scalable.