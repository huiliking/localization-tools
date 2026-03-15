import React, { useState } from "react";

// ⚠️ BEFORE: All strings hardcoded in English
// Run `npx ts-node localize.ts` to generate all locale files instantly

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");

  return (
    <div className="signup-container">

      {/* Header */}
      <header>
        <h1>Welcome to Acme</h1>
        <p>Already have an account? <a href="/login">Sign in</a></p>
      </header>

      {/* Hero */}
      <section className="hero">
        <h2>Start your free trial today</h2>
        <p>No credit card required. Cancel anytime.</p>
      </section>

      {/* Form */}
      <form onSubmit={(e) => e.preventDefault()}>

        <div className="field">
          <label htmlFor="name">Full name</label>
          <input
            id="name"
            type="text"
            placeholder="Enter your full name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="email">Work email</label>
          <input
            id="email"
            type="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            placeholder="At least 8 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <button type="submit">Create free account</button>

        <p className="terms">
          By signing up, you agree to our{" "}
          <a href="/terms">Terms of Service</a> and{" "}
          <a href="/privacy">Privacy Policy</a>.
        </p>

      </form>

      {/* Social proof */}
      <section className="social-proof">
        <p>Trusted by over 10,000 teams worldwide</p>
        <ul>
          <li>✓ Free 14-day trial</li>
          <li>✓ No setup fees</li>
          <li>✓ Cancel anytime</li>
        </ul>
      </section>

    </div>
  );
}
