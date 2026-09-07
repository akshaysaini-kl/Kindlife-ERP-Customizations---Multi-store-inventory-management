---
title: Frappe-First Development Policy
inclusion: auto
tags: [frappe, policy, development, standards]
---

# Frappe-First Development Policy

## 🎯 Core Principle

**ALWAYS use Frappe built-in utilities and functionalities FIRST.**

Only suggest external packages, libraries, or non-Frappe solutions after:
1. Confirming Frappe doesn't have equivalent functionality
2. Informing the user about the limitation
3. Getting explicit user approval

---

## ✅ Frappe Built-in Utilities Reference

### **1. Caching & Redis**
```python
# ✅ DO THIS (Frappe built-in)
frappe.cache().get_value(key)
frappe.cache().set_value(key, value, expires_in_sec=900)
frappe.cache().delete_value(key)
frappe.cache().ttl(key)

# ❌ DON'T DO THIS (External)
import redis
r = redis.Redis(host='localhost', port=6379)
r.set('key', 'value')
```

### **2. API Calls (Backend to Backend)**
```python
# ✅ DO THIS (Frappe built-in)
frappe.call('method.path', **kwargs)
frappe.get_request(url, params)

# ❌ DON'T DO THIS (External)
import requests
requests.get(url)
```

### **3. API Endpoints (Expose to Frontend)**
```python
# ✅ DO THIS (Frappe built-in)
@frappe.whitelist()
def my_api_method():
    return {"data": "value"}

# ❌ DON'T DO THIS (External)
from flask import Flask
app = Flask(__name__)
@app.route('/api')
def my_api():
    pass
```

### **4. Database Operations**
```python
# ✅ DO THIS (Frappe ORM)
doc = frappe.get_doc("DocType", "name")
frappe.db.get_value("DocType", "name", "field")
frappe.db.get_all("DocType", filters={...})
frappe.db.sql("SELECT ...", as_dict=True)

# ❌ DON'T DO THIS (Raw DB)
import mysql.connector
conn = mysql.connector.connect(...)
```

### **5. Background Jobs**
```python
# ✅ DO THIS (Frappe built-in)
frappe.enqueue(
    'module.path.function',
    queue='default',
    timeout=300,
    **kwargs
)

# ❌ DON'T DO THIS (External)
from celery import Celery
app = Celery('tasks')
@app.task
def my_task():
    pass
```

### **6. Real-time Updates**
```python
# ✅ DO THIS (Frappe built-in)
frappe.publish_realtime(
    event='my_event',
    message={'data': 'value'},
    user=frappe.session.user
)

# ❌ DON'T DO THIS (External)
import socketio
sio = socketio.Server()
```

### **7. File Operations**
```python
# ✅ DO THIS (Frappe built-in)
file_doc = frappe.get_doc({
    "doctype": "File",
    "file_name": "test.pdf",
    "content": file_content
})
file_doc.save()

# ❌ DON'T DO THIS (Direct filesystem)
with open('/path/to/file', 'wb') as f:
    f.write(content)
```

### **8. Email**
```python
# ✅ DO THIS (Frappe built-in)
frappe.sendmail(
    recipients=['user@example.com'],
    subject='Subject',
    message='Body'
)

# ❌ DON'T DO THIS (External)
import smtplib
server = smtplib.SMTP('smtp.gmail.com', 587)
```

### **9. Logging**
```python
# ✅ DO THIS (Frappe built-in)
frappe.log_error(message, title)
frappe.logger().info("message")
frappe.logger().error("error")

# ❌ DON'T DO THIS (Standard logging)
import logging
logging.basicConfig(...)
```

### **10. Date/Time Utilities**
```python
# ✅ DO THIS (Frappe built-in)
from frappe.utils import (
    now, today, nowdate, nowtime,
    add_days, add_months, get_datetime,
    format_date, format_datetime
)

# ❌ DON'T DO THIS (Standard library)
from datetime import datetime
datetime.now()
```

### **11. Validation**
```python
# ✅ DO THIS (Frappe built-in)
frappe.throw(_("Error message"))
frappe.msgprint(_("Warning message"))

# ❌ DON'T DO THIS (Standard exceptions)
raise ValueError("Error message")
```

### **12. Permissions**
```python
# ✅ DO THIS (Frappe built-in)
frappe.has_permission("DocType", "read", doc)
frappe.get_roles(user)
frappe.only_for("System Manager")

# ❌ DON'T DO THIS (Custom auth)
if user not in allowed_users:
    raise Exception("Not allowed")
```

---

## 🔍 Decision Tree

```
Need to implement feature X
         │
         ▼
Does Frappe have built-in for X?
         │
    ┌────┴────┐
    │         │
   YES       NO
    │         │
    ▼         ▼
Use Frappe   Search Frappe docs again
built-in     (frappe.io, github)
    │         │
    │    ┌────┴────┐
    │    │         │
    │   YES       NO
    │    │         │
    │    ▼         ▼
    │  Use it    Check Frappe source code
    │            (frappe/frappe repo)
    │             │
    │        ┌────┴────┐
    │        │         │
    │       YES       NO
    │        │         │
    │        ▼         ▼
    │      Use it    STOP! Inform user:
    │                "Frappe doesn't have X.
    │                 Options: A, B, C.
    │                 Which do you prefer?"
    │                      │
    │                      ▼
    │                Wait for approval
    │                      │
    └──────────────────────┴──────────────────┐
                                              │
                                              ▼
                                    Proceed with solution
```

---

## 📋 Pre-Implementation Checklist

Before writing any code, verify:

- [ ] Checked Frappe documentation (frappe.io/docs)
- [ ] Searched Frappe GitHub (frappe/frappe, frappe/erpnext)
- [ ] Looked at similar Frappe apps for patterns
- [ ] Confirmed Frappe doesn't have equivalent
- [ ] If external needed: Informed user with options
- [ ] If external needed: Got user approval
- [ ] Documented why Frappe built-in wasn't sufficient

---

## 🚫 Common Mistakes to Avoid

### **Mistake 1: Using Standard Python Instead of Frappe Utils**
```python
# ❌ WRONG
from datetime import datetime
now = datetime.now()

# ✅ CORRECT
from frappe.utils import now
current_time = now()
```

### **Mistake 2: Direct Database Access**
```python
# ❌ WRONG
import mysql.connector
conn = mysql.connector.connect(...)

# ✅ CORRECT
frappe.db.sql("SELECT ...", as_dict=True)
```

### **Mistake 3: Custom HTTP Server**
```python
# ❌ WRONG
from flask import Flask
app = Flask(__name__)

# ✅ CORRECT
@frappe.whitelist()
def my_api():
    pass
```

### **Mistake 4: External Task Queue**
```python
# ❌ WRONG
from celery import Celery
app = Celery('tasks')

# ✅ CORRECT
frappe.enqueue('module.function')
```

---

## 📚 Frappe Resources

### **Official Documentation**
- Main Docs: https://frappeframework.com/docs
- API Reference: https://frappeframework.com/docs/user/en/api
- Developer Guide: https://frappeframework.com/docs/user/en/guides

### **Source Code**
- Frappe Framework: https://github.com/frappe/frappe
- ERPNext: https://github.com/frappe/erpnext

### **Community**
- Forum: https://discuss.frappe.io/
- GitHub Issues: https://github.com/frappe/frappe/issues

---

## 🎓 Learning Path

### **When Starting a New Feature:**

1. **Read Frappe Docs First**
   - Check if feature exists
   - Look for similar examples

2. **Search Frappe Source Code**
   - How does Frappe implement similar features?
   - What utilities does Frappe provide?

3. **Check ERPNext Source**
   - ERPNext is built on Frappe
   - Great examples of Frappe patterns

4. **Ask Community**
   - Discuss forum
   - GitHub discussions

5. **Last Resort: External**
   - Only if Frappe truly doesn't have it
   - Get user approval first
   - Document reasoning

---

## ✅ Benefits of Frappe-First Approach

1. **Consistency** - Code follows Frappe patterns
2. **Maintenance** - Easier for Frappe developers to understand
3. **Upgrades** - Compatible with Frappe version updates
4. **Performance** - Optimized for Frappe's architecture
5. **Security** - Uses Frappe's security model
6. **Support** - Community familiar with Frappe patterns
7. **Dependencies** - Fewer external packages to manage

---

## 🔧 Exception Cases

### **When External Packages ARE Acceptable:**

1. **Frappe Explicitly Recommends It**
   - Example: ReportLab for PDF generation
   - Example: Pillow for image processing

2. **Standard Python Libraries**
   - json, datetime, os, sys (when Frappe utils don't cover it)
   - But prefer Frappe utils when available

3. **User Explicitly Approves**
   - After being informed of Frappe limitations
   - After discussing alternatives

---

## 📝 Template for Requesting External Package

When Frappe doesn't have functionality:

```
🚨 FRAPPE LIMITATION DETECTED

Feature Needed: [X]

Frappe Check:
- ❌ Not in frappe.utils
- ❌ Not in frappe core
- ❌ Not in ERPNext patterns

Proposed Solutions:
1. Option A: [Frappe workaround] (Pros/Cons)
2. Option B: [External package Y] (Pros/Cons)
3. Option C: [Custom implementation] (Pros/Cons)

Recommendation: [Option X] because [reason]

User Approval Required: YES/NO
```

---

## 🎯 Summary

**Golden Rule:** 
> "If Frappe has it, use it. If Frappe doesn't have it, ask first."

**Priority Order:**
1. ✅ Frappe built-in utilities
2. ✅ Frappe recommended packages
3. ⚠️ Standard Python (when Frappe doesn't cover it)
4. ⚠️ External packages (with user approval only)

---

**Last Updated:** 2026-05-07  
**Policy Version:** 1.0.0  
**Enforcement:** Automated via Kiro Hook
