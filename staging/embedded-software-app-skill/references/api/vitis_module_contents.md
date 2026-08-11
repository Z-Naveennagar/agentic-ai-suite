<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Python API — Client Lifecycle Commands

This document extracts the **top-level client lifecycle commands** from the provided module contents. These commands are foundational for **project management, automation, and scripting**, as they control how Vitis Python clients connect to and disconnect from the Vitis backend server.

> Scope note: Only the two commands shown in your excerpt are included.

---

## Module-Level APIs

### `vitis.create_client(port=None, host='localhost', workspace=None)`
Creates and initializes a Vitis client instance.

| Aspect | Details |
|---|---|
| Category | Client lifecycle / Session management |
| Purpose | Starts or connects to a Vitis backend server and establishes a client session |
| Typical use | First call in any Vitis Python automation or scripting workflow |

**Prototype**
```python
client = vitis.create_client(port=<port_number>, host=<host_name>, workspace=<workspace_location>)
```

**Optional Arguments**
- `workspace`: Workspace directory to be used by the client. Defaults to the **current working directory**.
- `port`: Port number of the Vitis server. Default is tool-selected.
- `host`: Hostname where the Vitis server is running. Default is `localhost`.

**Returns**
- Client instance

**Notes / Practical Guidance**
- If no arguments are provided, a local client is created using the current directory as the workspace.
- The returned client object is the entry point for interacting with projects, platforms, domains, and components.
- Multiple clients may connect to the same server unless explicitly terminated via `vitis.dispose()`.

**Example**
```python
client = vitis.create_client()
client = vitis.create_client(port=50762, workspace="/ws1/")
```

---

### `vitis.dispose()`
Closes all client connections and forcibly terminates the Vitis backend server.

| Aspect | Details |
|---|---|
| Category | Client lifecycle / Shutdown |
| Purpose | Terminates the Vitis server and invalidates all connected clients |
| Typical use | Final cleanup step in scripts, CI jobs, or controlled shutdown scenarios |

**Prototype**
```python
vitis.dispose()
```

**Arguments**
- None

**Returns**
- None

**Important Behavior**
- All connected clients (including those created in other processes) become **non-functional** after this call.
- Use with care in shared or multi-user environments.

**Example**
```python
vitis.dispose()
```

---

## Typical Usage Pattern
```python
import vitis

client = vitis.create_client(workspace="/my/workspace")
# ... project, platform, domain, component operations ...
vitis.dispose()
```

This pattern is commonly used in **automation scripts, CI pipelines, and batch builds** to ensure deterministic startup and shutdown of the Vitis environment.
