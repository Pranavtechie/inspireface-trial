# Axon Attendance System

## Overview

The Axon Attendance System is a comprehensive face recognition-based attendance tracking solution designed specifically for the Vicharak Axon - RK3588 (Rockchip) device. This system provides automated attendance marking for cadets and employees at Korukonda Coaching Centre using advanced face recognition technology.

## System Architecture

### Hardware Platform

- **Device**: Vicharak Axon - RK3588 (Rockchip)
- **Architecture**: ARM64 (aarch64)
- **OS**: Linux
- **Special Optimizations**: Rockchip-specific RGA (Raster Graphics Acceleration) backend optimizations for face detection

### Software Architecture

The system follows a **multi-process architecture** with two main processes:

1. **Flask API Server** (`src/api/server.py`)

   - RESTful API endpoints for enrollment and data management
   - Handles communication with external backend (`api.korukondacoachingcentre.com`)
   - Manages face enrollment from web application
   - Processes attendance data and syncs with remote database

2. **PySide6 UI Application** (`src/ui/app.py`)
   - Full-screen Qt-based user interface
   - Real-time face recognition display
   - User interaction and status display
   - Session management interface

### Core Components

#### 1. Face Recognition Engine (`src/core/face_recognizer.py`)

- **SDK**: InspireFace with Megatron model
- **Features**:
  - Real-time face detection and recognition
  - Face enrollment from images
  - Feature extraction and matching
  - Rockchip-optimized processing
- **Database**: FAISS-based feature database with SQLite persistence
- **Threshold**: 0.6 similarity threshold for recognition

#### 2. Database Schema (`src/schema.py`)

- **Person**: Stores cadet/employee information
  - `uniqueId`, `name`, `admissionNumber`, `roomId`, `pictureFileName`, `personType`, `syncedAt`
- **Room**: Hostel room information
  - `roomId`, `roomName`, `syncedAt`
- **CadetAttendance**: Attendance records
  - `personId`, `attendanceTimeStamp`, `sessionId`, `syncedAt`
- **Session**: Active session management
  - `id`, `name`, `startTimestamp`, `plannedEndTimestamp`, `plannedDurationInMinutes`, `actualEndTimestamp`, `syncedAt`

#### 3. Inter-Process Communication (`src/ipc/`)

- **Protocol**: Unix Domain Sockets (`/tmp/axon-attendance.sock`)
- **Message Format**: JSON payloads
- **Features**:
  - Real-time communication between UI and API server
  - Broadcast messaging to all connected UI clients
  - Asynchronous message handling

#### 4. Configuration Management (`src/config.py`)

- Centralized configuration for all system components
- Path management for data, models, and enrollment images
- System-specific parameters and thresholds

## Operation Flow

### 1. System Startup

```
1. Flask API Server starts (port 1340)
2. Socket server initializes for IPC
3. PySide6 UI application launches
4. UI connects to socket server
5. Face recognition engine initializes (if active session exists)
```

### 2. Session Management

- **Session-Based Operation**: System only activates face recognition when an active session exists
- **Session Source**: Sessions are received from `api.korukondacoachingcentre.com`
- **Power Management**: Prevents unnecessary compute-intensive operations when no session is active
- **UI Display**: Shows "empty session" message when no active session exists

### 3. Face Enrollment Process

```
1. Web application sends enrollment request to Flask API
2. API downloads image from provided URL
3. Image is cached locally in enrollment_images directory
4. Person record is created/updated in local database
5. Face features are extracted and added to FAISS database
6. UI is notified of successful enrollment via IPC
```

### 4. Attendance Recognition Flow

```
1. Camera captures video frame
2. Face detection identifies faces in frame
3. Feature extraction for each detected face
4. FAISS search for matching features
5. If match found (confidence > 0.6):
   - Attendance record created in local database
   - Remote API call to sync with backend
   - UI updated with recognition result
6. Frame displayed with bounding boxes and names
```

### 5. Data Synchronization

- **Bidirectional Sync**: Local SQLite ↔ Remote PostgreSQL (Neon DB)
- **Sync Strategy**: Based on `syncedAt` timestamps
- **Failure Handling**: Local persistence with retry mechanism
- **Sync Endpoints**:
  - Enrollment data sync
  - Attendance records sync
  - Session data sync

## Key Features

### 1. Rockchip Optimizations

- **RGA Backend**: Hardware-accelerated image processing
- **Stride Alignment**: 16-byte alignment for RGB888 processing
- **Preview Size**: 640px internal preview for better detection
- **Minimum Face Size**: 16px filter to avoid stride issues

### 2. Session-Based Architecture

- **Resource Management**: Face recognition only active during sessions
- **Power Efficiency**: Reduces unnecessary compute load
- **Session Validation**: Ensures attendance is only marked during valid sessions

### 3. Real-Time Communication

- **IPC Socket**: Unix domain sockets for low-latency communication
- **Broadcast Messaging**: Real-time updates to all UI clients
- **JSON Payloads**: Structured message format for type safety

### 4. Robust Error Handling

- **Network Resilience**: Timeout handling for remote API calls
- **Image Processing**: Graceful handling of corrupted or invalid images
- **Database Operations**: Transaction safety and conflict resolution

## Deployment Architecture

### System Services

The system will be deployed as systemctl services on the Vicharak device:

1. **axon-attendance-api.service**

   - Flask API server
   - Socket server for IPC
   - Database management

2. **axon-attendance-ui.service**
   - PySide6 UI application
   - Full-screen display
   - User interaction handling

### Data Storage

- **Local Database**: SQLite (`data/attendance.db`)
- **Face Features**: FAISS database (`data/inspireface.db`)
- **Enrollment Images**: Local cache (`data/enrollment_images/`)
- **ID Mapping**: JSON file (`data/id_name_map.json`)

### External Dependencies

- **Backend API**: `api.korukondacoachingcentre.com`
- **Image Storage**: Remote image URLs for enrollment
- **Session Management**: Remote session data

## Development Environment

### Package Management

- **Package Manager**: `uv` for fast Python package management
- **Python Version**: 3.10.17
- **Key Dependencies**:
  - `inspireface`: Face recognition SDK
  - `pyside6`: Qt-based UI framework
  - `flask`: Web API framework
  - `peewee`: ORM for database operations
  - `opencv-python`: Computer vision operations

### Code Organization

```
src/
├── api/           # Flask API server
├── core/          # Face recognition engine
├── ipc/           # Inter-process communication
├── ui/            # PySide6 UI application
├── config.py      # Configuration management
├── schema.py      # Database models
└── utils.py       # Utility functions
```

## Important Design Principles

1. **Session-Based Operation**: Face recognition only active during valid sessions
2. **Power Efficiency**: Optimized for embedded Rockchip hardware
3. **Offline Capability**: Local database with sync when online
4. **Real-Time Performance**: Optimized for live video processing
5. **Scalable Architecture**: Modular design for easy maintenance and updates

This architecture ensures reliable, efficient, and user-friendly attendance tracking while maintaining system stability and power efficiency on the Vicharak Axon device.
