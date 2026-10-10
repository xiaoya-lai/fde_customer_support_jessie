Alice never sees Bob's laptop.

# BUILD_LOG

> Copy this file to `BUILD_LOG.md`. Fill in each stage **as you go**, not at the end: the
> decision **before** you prompt your agent, the prediction **before** you run the check.
>
> This is your record of what *you* understood. A person reads it for `G-DESIGN` and
> `G-ENFORCE`. Your coding agent is instructed not to write it for you; if the words aren't
> yours, it shows.
>
> Three lines per part is plenty. "I expected X, got Y, because Z" beats a paragraph.

---

## Stage 1: the database

- **I decided:** drop-and-recreate seed.sql + reset cmd. If seeded twice without running drop, the order sequence would not be correct.
- **I predicted: should be able to see the correct counts, and correct number of orders (e.g. 17 rows). I thought it would accept the insert because I didn't notice the error of enum by my human eyes.**
- **What happened (paste output):**

 count 

-------

    10

(1 row)



order_id, customer_email, status from customer_orders order by order_id;"

 order_id |     customer_email      |   status   

----------+-------------------------+------------

        1 | [alice.jones@example.com](mailto:alice.jones@example.com) | DELIVERED

        2 | [alice.jones@example.com](mailto:alice.jones@example.com) | DELIVERED

        3 | [alice.jones@example.com](mailto:alice.jones@example.com) | SHIPPED

        4 | [alice.jones@example.com](mailto:alice.jones@example.com) | PROCESSING

        5 | [bob.smith@techmail.com](mailto:bob.smith@techmail.com)  | DELIVERED

        6 | [bob.smith@techmail.com](mailto:bob.smith@techmail.com)  | CANCELLED

        7 | [bob.smith@techmail.com](mailto:bob.smith@techmail.com)  | PROCESSING

        8 | [charlie.d@webmail.com](mailto:charlie.d@webmail.com)   | DELIVERED

        9 | [diana.prince@hero.net](mailto:diana.prince@hero.net)   | DELIVERED

       10 | [diana.prince@hero.net](mailto:diana.prince@hero.net)   | RETURNED

       11 | [evan.g@bizcorp.com](mailto:evan.g@bizcorp.com)      | SHIPPED

       12 | [fiona.shrek@swamp.com](mailto:fiona.shrek@swamp.com)   | CANCELLED

       13 | [george.j@jungle.com](mailto:george.j@jungle.com)     | PROCESSING

       14 | [hannah.m@school.edu](mailto:hannah.m@school.edu)     | DELIVERED

       15 | [ian.malcolm@chaos.com](mailto:ian.malcolm@chaos.com)   | DELIVERED

       16 | [julia.child@kitchen.com](mailto:julia.child@kitchen.com) | DELIVERED

       17 | [julia.child@kitchen.com](mailto:julia.child@kitchen.com) | PROCESSING

(17 rows)



ERROR:  new row for relation "actions_log" violates check constraint "actions_log_action_type_check"

DETAIL:  Failing row contains (1, 2026-10-09 21:39:45.114109-07, x, RETURN_ITEM, {}).

## Stage 2: the tools, and where access control lives

- **Before reading SPEC R-1, I thought ownership belonged in:**
- **I decided:**
- **What happened (order 5 as alice):**



## Stage 3: the agent, and a bare CLI

- **I decided (tools loaded, how the email is bound):**
- **I predicted the "order 5 for bob" request would:**
- **What happened:**



## Stage 4: the pipeline and its events

- **My hand-sketched CLI lines:**
- **I predicted the first event after the agent stage would be:**
- **What happened:**



## Stage 5: one trace per turn

- **I decided (what goes in span attributes, who can see Phoenix):**
- **Trace id:**
- **One thing the trace showed that the reply didn't:**



## Stage 6: Sanitizer and Security Judge

- **I decided (who may block, which A2A method):**
- **Predicted vs actual X01 latency:**
- **When I stopped the Judge, my pipeline first:**
- **Failing trajectory saved at:**



## Stage 7: the Guardrail

- **Three messages that must pass / three that must not (written before the prompt):**
- **False blocks / off-topic blocks, per prompt version:**

  | Version | What I changed | Legit false blocks | Off-topic blocked |
  | ------- | -------------- | ------------------ | ----------------- |
  | v1      |                |                    |                   |




## Stage 8: Masker and memory

- **I decided (what counts as PII, the cutoff):**
- **My planted memory's score, and whether my cutoff kept it:**
- **What the Masker reported on my PII test:**



## Stage 9: the web UI

- **My sketch, in words:**
- **Something the UI shows that the CLI doesn't (feature or leak?):**



## Stage 10: the eval runner

- **How I handled the memory waits:**
- **First run's failing rows, and what I changed:**
- **Second run: see** `reports/eval.json` **(don't retype numbers here).**
- **Successful turn I read end to end (trace id), and what it taught me:**
- **Failing turn I read end to end (trace id), and what it taught me:**

