# Alternative Approach

Basically everything here is about fighting the problems of trying to use agents together and under a subscription model.

* "-p" mode (prompt payload) as default to avoid having to inject /clear commands to avoid context growth
* probably sqlite to store various information:
  * each DAG edge: parent,child
  * entity ts,id,agenttype,options,session_id,payload ... consider always joining to DAG edge?
  * each node is a -p payload agent call
  * if session_id is null you have to somehow obtain the session id AFTER creation and log it
  * if session_id is not null you automatically inherit the previous context and have that previous call as a parent implicitly
  * comms log:
    * ts,from,to,payload
    * somehow you have to "consume" from it at the right time in the right way. Agents are quite annoying at this.
