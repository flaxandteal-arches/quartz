// ***********************************************
// This example commands.js shows you how to
// create various custom commands and overwrite
// existing commands.
//
// For more comprehensive examples of custom
// commands please read more here:
// https://on.cypress.io/custom-commands
// ***********************************************
//
//
// -- This is a parent command --
// Cypress.Commands.add("login", (email, password) => { ... })
//
//
// -- This is a child command --
// Cypress.Commands.add("drag", { prevSubject: 'element'}, (subject, options) => { ... })


Cypress.Commands.add("login", () => {
    cy.visit('/auth/?next=/index.htm');

    cy.get('input[name="username"]').type(`admin`);
    cy.get('input[name="password"]').type(`admin{enter}`);

    // Wait for the post-login redirect so the session cookie is set
    // before any subsequent cy.request() calls.
    cy.url().should('include', '/index.htm');
});
