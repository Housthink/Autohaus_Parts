from odoo import models


class ProductPublicCategory(models.Model):
    _inherit = 'product.public.category'

    def _get_preview_products(self):
        """Return ``{category_id: product.template}`` with one preview product
        (that has an image) per category in ``self``.

        The shop category filmstrip used to run one ``search`` per category
        (``public_categ_ids child_of`` + ``image_128 != False``). Each of those
        queries costs an ``EXISTS`` on ``ir_attachment``, so with many
        categories and a large catalog it scaled badly and could time out the
        ``/shop`` page. This does the same job in a bounded number of queries.
        """
        previews = {
            category.id: self.env['product.template'].sudo().browse()
            for category in self
        }
        if not self:
            return previews

        # All descendant categories in a single query.
        descendants = self.sudo().search([('id', 'child_of', self.ids)])
        # Candidate products (with an image) in a single query.
        candidates = self.env['product.template'].sudo().search([
            ('public_categ_ids', 'in', descendants.ids),
            ('image_128', '!=', False),
        ])
        if not candidates:
            return previews

        # parent_path prefix per requested category, to resolve "child_of" in
        # Python without extra queries.
        prefixes = {
            category.id: (category.parent_path or '') + str(category.id) + '/'
            for category in self
        }
        remaining = set(self.ids)
        for product in candidates:
            if not remaining:
                break
            for category in product.public_categ_ids:
                if not remaining:
                    break
                path = (category.parent_path or '') + str(category.id) + '/'
                for category_id in tuple(remaining):
                    if category.id == category_id or path.startswith(prefixes[category_id]):
                        previews[category_id] = product
                        remaining.discard(category_id)
                        break
        return previews
