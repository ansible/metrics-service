# System-Defined Tasks Implementation

A comprehensive system for automatically creating and protecting essential tasks that ensure critical functionality like cleanup and metrics collection.

## ✨ **Overview**

The system tasks framework ensures that essential tasks are **always present** and **protected from deletion**, providing a reliable foundation for metrics service operation.

## 🎯 **System Tasks Created**

### **🧹 Maintenance Tasks**

1. **Daily Task Cleanup** 
   - **Function**: `cleanup_old_tasks`
   - **Schedule**: Daily at 2 AM (`0 2 * * *`)
   - **Purpose**: Removes completed/failed tasks older than 5 days (preserves recurring tasks)
   - **Parameters**: `{"days_old": 5, "preserve_recurring": true}`

2. **Weekly Maintenance Cleanup**
   - **Function**: `cleanup_old_data` 
   - **Schedule**: Weekly on Sunday at 3 AM (`0 3 * * 0`)
   - **Purpose**: Cleans up old system data, logs, and temporary files
   - **Parameters**: `{"days_old": 30, "data_types": ["logs", "temp_files", "cache"]}`

### **📊 Metrics Collection Tasks**

3. **Anonymous Metrics Collection**
   - **Function**: `collect_anonymous_metrics`
   - **Schedule**: Every 6 hours (`0 */6 * * *`)
   - **Purpose**: Collects anonymous system metrics for monitoring
   - **Parameters**: `{}`

4. **System Configuration Collection**
   - **Function**: `collect_config_metrics`
   - **Schedule**: Weekly on Sunday at 4 AM (`0 4 * * 0`)
   - **Purpose**: Collects system configuration information
   - **Parameters**: `{}`

5. **Host Metrics Collection**
   - **Function**: `collect_host_metrics`
   - **Schedule**: Every 4 hours (`0 */4 * * *`)
   - **Purpose**: Collects host performance and system metrics
   - **Parameters**: `{}`

## 🛠️ **Technical Implementation**

### **Database Schema**
- Added `is_system_task` boolean field to Task model
- Migration: `0002_add_system_task_flag.py`
- Default: `False` for user-created tasks

### **Task Configuration**
```python
SYSTEM_TASKS = [
    {
        "name": "Daily Task Cleanup",
        "function_name": "cleanup_old_tasks",
        "description": "Automatically removes completed and failed tasks...",
        "task_data": {"days_old": 5, "preserve_recurring": True},
        "cron_expression": "0 2 * * *",
        "is_recurring": True,
        "priority": 2,
        "is_enabled": True,
        "category": "maintenance"
    },
    # ... more tasks
]
```

### **Automatic Creation**
- **App Startup**: Tasks auto-created when Django app starts
- **Management Command**: `python manage.py init_system_tasks`
- **Smart Updates**: Only modifies tasks when configuration changes
- **Database-Safe**: Handles missing database gracefully

### **Protection Mechanisms**

#### **Model-Level Protection**
```python
def can_delete(self) -> bool:
    """System tasks cannot be easily deleted."""
    return not self.is_system_task

def can_modify(self) -> bool:
    """System tasks have limited modification capabilities."""
    return not self.is_system_task
```

#### **API Protection**
- **DELETE Protection**: `perform_destroy()` blocks system task deletion
- **UPDATE Protection**: `perform_update()` prevents modification of critical fields
- **Force Delete**: Admin endpoint with explicit confirmation required
- **Protected Fields**: `function_name`, `is_system_task`, `cron_expression`, `is_recurring`

#### **Dashboard Protection**
- **Visual Indicators**: 🔧 icon and "SYSTEM" badge for system tasks
- **Protected Actions**: Delete button replaced with "🔒 Protected" for system tasks
- **Clear Messaging**: Tooltips explain protection rationale

## 🎨 **User Experience**

### **Dashboard Enhancements**

**System Task Indicators**:
- 🔧 **Icon**: Appears before system task names
- **SYSTEM Badge**: Blue badge identifying system tasks
- **Protected Status**: "🔒 Protected" instead of delete button
- **Tooltips**: Hover text explains protection

**Task Details Modal**:
- **Task Type**: Shows "SYSTEM TASK" badge for system tasks
- **Enhanced Info**: Clear indication of protection status

### **Management Command**

```bash
# Initialize system tasks
python manage.py init_system_tasks

# Dry run (see what would happen)
python manage.py init_system_tasks --dry-run

# List current system tasks
python manage.py init_system_tasks --list

# Force update all tasks
python manage.py init_system_tasks --force
```

**Command Output Example**:
```
🔧 System Tasks Initialization
==================================================
📊 Results:
  ✅ Created: 5 tasks
  🔄 Updated: 0 tasks
  ⏭️  Skipped: 0 tasks (no changes needed)

📋 Task Details:
  ✅ Created: Daily Task Cleanup
  ✅ Created: Anonymous Metrics Collection
  ✅ Created: System Configuration Collection
  ✅ Created: Host Metrics Collection
  ✅ Created: Weekly Maintenance Cleanup

==================================================
✅ Processed 5 system tasks in 0.25 seconds
💡 Run 'python manage.py init_system_tasks --list' to see current status
```

## 🚀 **API Endpoints**

### **New Endpoints**

1. **System Tasks Info**: `GET /api/v1/tasks/system_tasks_info/`
   - Returns system task status and configuration
   - Useful for monitoring and administration

2. **Force Delete**: `DELETE /api/v1/tasks/{id}/force_delete/`
   - Admin-only endpoint for emergency system task deletion
   - Requires explicit confirmation: `{"force_confirm": true}`

### **Enhanced Serialization**
- **`can_delete`**: Boolean indicating if task can be deleted
- **`can_modify`**: Boolean indicating if task can be modified
- **`is_system_task`**: Boolean marking system tasks
- **Read-only Fields**: System task flag is protected from user modification

## 🛡️ **Security & Safety Features**

### **Multi-Layer Protection**

1. **Database Level**: `is_system_task` field prevents easy identification bypass
2. **Model Level**: `can_delete()` and `can_modify()` methods enforce business rules
3. **API Level**: `perform_destroy()` and `perform_update()` block unauthorized changes
4. **UI Level**: Dashboard shows protection status and disables dangerous actions

### **Safe Configuration Updates**
- **Smart Merging**: Only updates changed configuration fields
- **Preserves User Data**: User modifications to allowed fields are maintained
- **Version Safe**: Handles configuration schema changes gracefully

### **Emergency Procedures**
- **Force Delete**: Available for critical situations with admin confirmation
- **Recreation**: System tasks automatically recreated on next startup
- **Monitoring**: System task status visible in dashboard and API

## 📈 **Benefits**

### **For System Administrators**
- ✅ **Guaranteed Functionality**: Critical tasks can't be accidentally deleted
- ✅ **Automatic Setup**: New installations get essential tasks immediately
- ✅ **Easy Monitoring**: Clear visibility into system task status
- ✅ **Safe Updates**: Configuration changes applied without data loss

### **For End Users**
- ✅ **Protected Experience**: Can't break system by deleting wrong tasks
- ✅ **Clear Indicators**: System tasks are clearly marked and explained
- ✅ **Maintained Service**: Cleanup and metrics continue automatically
- ✅ **Professional UI**: Protection enhances rather than restricts interface

### **For Developers**
- ✅ **Extensible Framework**: Easy to add new system tasks
- ✅ **Configuration Driven**: No code changes needed for task updates
- ✅ **Database Safe**: Handles migration and startup scenarios gracefully
- ✅ **Well Tested**: Comprehensive protection at all levels

## 🔄 **Usage Scenarios**

### **Initial Setup**
1. Run migrations: `python manage.py migrate`
2. Initialize system tasks: `python manage.py init_system_tasks`
3. Tasks automatically created and scheduled
4. Dashboard shows protected system tasks

### **Configuration Updates**
1. Modify `SYSTEM_TASKS` configuration
2. Restart application (auto-updates on startup)
3. Or run: `python manage.py init_system_tasks`
4. Only changed fields are updated

### **Monitoring**
1. Dashboard shows system task status with protection indicators
2. API endpoint: `GET /api/v1/tasks/system_tasks_info/`
3. Management command: `python manage.py init_system_tasks --list`

### **Emergency Situations**
1. Use force delete API with confirmation if absolutely necessary
2. System tasks will be recreated on next startup
3. Consider disabling rather than deleting when possible

## 🎯 **Result**

The system now provides a **professional-grade task management system** with:

- **🔧 5 Essential System Tasks** automatically created and protected
- **🛡️ Multi-Layer Protection** preventing accidental deletion or misconfiguration  
- **🎨 Enhanced Dashboard** with clear system task indicators and protection status
- **⚡ Automatic Startup** ensuring critical tasks are always present
- **🔧 Management Tools** for administrators to monitor and maintain system tasks

**Critical functionality like cleanup and metrics collection is now guaranteed to be available and protected from user error!** 🎉