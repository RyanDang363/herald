![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:transportation](https://img.shields.io/badge/transportation-FF6B35)
![tag:schedule-assistant](https://img.shields.io/badge/schedule_assistant-4CAF50)
![tag:caltrain](https://img.shields.io/badge/caltrain-E31837)
![tag:ai-powered](https://img.shields.io/badge/ai_powered-9C27B0)

# 🚂 Caltrain Agent

Your intelligent companion for navigating the Caltrain system! Just ask in natural language and get instant train schedules with departure times, arrivals, and travel durations. Whether you need trains for today, tomorrow, or a specific date like "October 13th," I'll understand and help you plan your journey.

## What I Can Do

✨ **Natural Conversation**: Talk to me naturally! Say "I need to get to Mountain View from San Carlos after 1 pm" and I'll understand exactly what you need.

📅 **Flexible Dates**: Ask for trains "today," "tomorrow," or specific dates like "October 13th" or "Oct 20" - I automatically figure out if it's a weekday or weekend schedule.

⏰ **Smart Time Filtering**: Need trains "after 5pm" or "between 8 and 9 am"? I'll show you only the trains that match your time window.

🚉 **All 30 Stations**: From San Francisco to Gilroy, I know every Caltrain station and can handle nicknames and variations.

💬 **Helpful Follow-ups**: If you forget to mention where you're starting from or heading to, I'll ask! We can have a natural back-and-forth conversation.

## Example Queries

**Simple Routes:**
- "Next train from SF to Palo Alto"
- "Trains from Sunnyvale to Santa Clara"
- "Mountain View to San Jose"

**With Time Preferences:**
- "Trains after 5pm from SF to Palo Alto"
- "Between 8 and 9 am from Sunnyvale to Santa Clara"
- "Morning trains from San Carlos to Mountain View"

**With Specific Dates:**
- "Tomorrow morning, Sunnyvale to Santa Clara"
- "Trains from Palo Alto to San Jose on October 13th"
- "I'm planning to go from Hillsdale to Santa Clara on October 13th after 8 am"

**Natural Conversation:**
- "I need to get to Mountain View from San Carlos after 1 pm today"
- "When is the train available between 8 and 9 am tomorrow from Sunnyvale to Santa Clara?"

## Sample Responses

### Example 1: Time Range Query

**You ask**: "When is the train available between 8 and 9 am tomorrow from Sunnyvale to Santa Clara?"

**I respond**:
```
🚂 Tomorrow's Trains: Sunnyvale → Santa Clara
📅 Weekend schedule | 🕐 Tomorrow: Saturday, Oct 11
⏰ Time range: 8:00 AM - 9:00 AM

🚆 Train 602 (Local)
   Departs: 8:59 AM → Arrives: 9:07 AM (8 min)

💡 Check caltrain.com for real-time updates.

Need another route? Just ask! 🚆
```

### Example 2: Specific Date Query

**You ask**: "I am planning to go from Hillsdale to Santa Clara on October 13th after 8 am which train I should take"

**I respond**:
```
🚂 Monday, Oct 13's Trains: Hillsdale → Santa Clara
📅 Weekday schedule | 🕐 Monday, Oct 13

🚆 Train 102 (Local)
   Departs: 8:14 AM → Arrives: 8:52 AM (38 min)

🚆 Train 104 (Local)
   Departs: 8:44 AM → Arrives: 9:22 AM (38 min)

🚆 Train 230 (Limited)
   Departs: 9:05 AM → Arrives: 9:35 AM (30 min)

💡 Check caltrain.com for real-time updates.

Need another route? Just ask! 🚆
```

### Example 3: Today's Schedule

**You ask**: "I need to get to Mountain View from San Carlos after 1 pm today"

**I respond**:
```
🚂 Today's Trains: San Carlos → Mountain View
📅 Weekday schedule | 🕐 Today: Friday, Oct 10

🚆 Train 130 (Local)
   Departs: 1:03 PM → Arrives: 1:24 PM (21 min)

🚆 Train 132 (Local)
   Departs: 1:33 PM → Arrives: 1:54 PM (21 min)

🚆 Train 134 (Local)
   Departs: 2:03 PM → Arrives: 2:24 PM (21 min)

💡 Check caltrain.com for real-time updates.

Need another route? Just ask! 🚆
```

### Example 4: Conversational Help

**You ask**: "I need to go to San Jose"

**I respond**:
```
📍 Got it - you're heading to San Jose!

Where are you starting from?
```

**You say**: "Palo Alto"

**I respond**: *[Shows complete train schedule from Palo Alto to San Jose]*
