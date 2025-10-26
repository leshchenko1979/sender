# Project Brief: Telegram Message Sender

## Project Overview
A Telegram message automation system that sends scheduled messages and forwards content to various chats using multiple Telegram accounts. The system integrates with Google Sheets for configuration management and Supabase for logging.

## Core Functionality
- **Scheduled Messaging**: Send text messages to Telegram chats/channels on a cron schedule
- **Message Forwarding**: Forward messages from one chat to another (including media groups)
- **Multi-Account Support**: Use multiple Telegram accounts for different messaging tasks
- **Auto-Join**: Automatically join chats when needed before sending/forwarding
- **Error Handling**: Comprehensive error handling with automatic schedule adjustment for slow mode
- **Forum Topic Support**: Send messages to specific topics in Telegram supergroups

## Key Components
- **SenderAccount**: Custom Telegram account class with auto-join functionality
- **Client**: Manages multiple settings and Google Sheets integration
- **Setting**: Individual message configuration with cron scheduling
- **Supabase Integration**: Logging and file system for session management

## Configuration Sources
- **Google Sheets**: Main configuration via spreadsheet URLs
- **clients.yaml**: Client definitions with alert settings
- **Environment Variables**: Telegram API credentials, Supabase config

## Target Use Cases
- Marketing message automation
- Content distribution across multiple channels
- Scheduled announcements
- Cross-platform message forwarding


