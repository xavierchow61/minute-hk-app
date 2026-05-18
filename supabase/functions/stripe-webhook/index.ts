// Minute.hk - Stripe Webhook Handler (Supabase Edge Function)
// Deploy: supabase functions deploy stripe-webhook --no-verify-jwt
// 或者 via Supabase Dashboard → Edge Functions → New function

import Stripe from "https://esm.sh/stripe@17?target=denonext";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// ============ Setup ============
const stripe = new Stripe(Deno.env.get("STRIPE_SECRET_KEY")!, {
  apiVersion: "2024-12-18.acacia",
  httpClient: Stripe.createFetchHttpClient(),
});

const cryptoProvider = Stripe.createSubtleCryptoProvider();

const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, // 用 service role，繞過 RLS
);

const webhookSecret = Deno.env.get("STRIPE_WEBHOOK_SECRET")!;

// ============ Handler ============
Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const signature = req.headers.get("Stripe-Signature");
  if (!signature) {
    return new Response("Missing Stripe-Signature header", { status: 400 });
  }

  const body = await req.text();

  // Verify webhook signature
  let event: Stripe.Event;
  try {
    event = await stripe.webhooks.constructEventAsync(
      body,
      signature,
      webhookSecret,
      undefined,
      cryptoProvider,
    );
  } catch (err) {
    console.error("Webhook signature verification failed:", err.message);
    return new Response(`Webhook Error: ${err.message}`, { status: 400 });
  }

  console.log(`📥 Received event: ${event.type}`);

  try {
    switch (event.type) {
      case "checkout.session.completed": {
        const session = event.data.object as Stripe.Checkout.Session;
        await handleCheckoutCompleted(session);
        break;
      }

      case "customer.subscription.created":
      case "customer.subscription.updated": {
        const sub = event.data.object as Stripe.Subscription;
        await handleSubscriptionUpdated(sub);
        break;
      }

      case "customer.subscription.deleted": {
        const sub = event.data.object as Stripe.Subscription;
        await handleSubscriptionDeleted(sub);
        break;
      }

      case "invoice.payment_failed": {
        const invoice = event.data.object as Stripe.Invoice;
        console.log(`⚠️ Payment failed for customer ${invoice.customer}`);
        // 可選：downgrade or 通知用戶
        break;
      }

      default:
        console.log(`Unhandled event type: ${event.type}`);
    }

    return new Response(JSON.stringify({ received: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    console.error("Error handling webhook:", err);
    return new Response(
      JSON.stringify({ error: (err as Error).message }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
});

// ============ Event Handlers ============

async function handleCheckoutCompleted(session: Stripe.Checkout.Session) {
  // user_id 可以喺 client_reference_id 或 metadata 攞到
  const userId = session.client_reference_id ||
    (session.metadata && session.metadata["user_id"]);
  const plan = (session.metadata && session.metadata["plan"]) || "pro";

  if (!userId) {
    console.error("No user_id in checkout session", session.id);
    return;
  }

  console.log(`✅ Upgrade ${userId} → ${plan}`);

  const { error } = await supabase
    .from("user_plans")
    .update({
      plan: plan,
      stripe_customer_id: session.customer as string,
      stripe_subscription_id: session.subscription as string,
      updated_at: new Date().toISOString(),
    })
    .eq("user_id", userId);

  if (error) {
    console.error("Update user_plans error:", error);
    throw error;
  }
}

async function handleSubscriptionUpdated(sub: Stripe.Subscription) {
  const userId = sub.metadata && sub.metadata["user_id"];
  if (!userId) {
    console.log("No user_id in subscription metadata", sub.id);
    return;
  }

  const status = sub.status;
  const plan = (sub.metadata && sub.metadata["plan"]) || "pro";

  // Active 或 trialing → 用 paid plan；其他狀態 → 返 free
  const newPlan = (status === "active" || status === "trialing")
    ? plan
    : "free";

  console.log(`🔄 Subscription ${sub.id} status=${status} → plan=${newPlan}`);

  const { error } = await supabase
    .from("user_plans")
    .update({
      plan: newPlan,
      stripe_subscription_id: sub.id,
      subscription_ends_at: sub.current_period_end
        ? new Date(sub.current_period_end * 1000).toISOString()
        : null,
      updated_at: new Date().toISOString(),
    })
    .eq("user_id", userId);

  if (error) {
    console.error("Update subscription error:", error);
    throw error;
  }
}

async function handleSubscriptionDeleted(sub: Stripe.Subscription) {
  const userId = sub.metadata && sub.metadata["user_id"];
  if (!userId) return;

  console.log(`❌ Cancel subscription for user ${userId}`);

  const { error } = await supabase
    .from("user_plans")
    .update({
      plan: "free",
      subscription_ends_at: null,
      updated_at: new Date().toISOString(),
    })
    .eq("user_id", userId);

  if (error) {
    console.error("Downgrade error:", error);
    throw error;
  }
}
