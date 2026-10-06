import { index, pgTable, text, timestamp } from "drizzle-orm/pg-core";
import { conversations } from "./conversations";

export const messages = pgTable(
  "messages",
  {
    id: text("id").primaryKey(),
    conversationId: text("conversation_id")
      .notNull()
      .references(() => conversations.id, { onDelete: "cascade" }),
    role: text("role").notNull(),
    content: text("content").notNull(),
    model: text("model"),
    skillUsed: text("skill_used"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    conversationCreatedIndex: index("messages_conversation_created_idx").on(
      table.conversationId,
      table.createdAt,
    ),
  }),
);

export type Message = typeof messages.$inferSelect;
export type NewMessage = typeof messages.$inferInsert;